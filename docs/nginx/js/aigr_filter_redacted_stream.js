/**
 * NJS Guardrail for chat completion (request-only).
 * 场景：Client -> NGINX (njs 做请求扫描/脱敏) -> proxy_pass LLM Provider（保持 SSE 流式响应）
 *
 * 用法建议：
 *   location /v1/chat/completions {
 *       js_access guardrail.requestGuard;
 *       # 这里直接 proxy_pass 到 LLM，响应不再经过 njs，保留 SSE streaming
 *   }
 */

function requestGuard(r) {
    // Debug 开关来自 nginx 变量：set $enable_debug_logs 1;
    let debugEnabled = r.variables.enable_debug_logs === "1";

    function debugLog(msg) {
        if (debugEnabled) {
            r.log(msg);
        }
    }

    // 读取并解析请求体
    let body;
    try {
        body = JSON.parse(r.requestText);
    } catch (e) {
        r.error("Guardrail: Failed to parse request body: " + e);
        r.return(400, JSON.stringify({ error: "Invalid JSON in request body" }));
        return;
    }

    // 提取最后一条 user message content
    let userInput = "";
    if (body.messages && Array.isArray(body.messages) && body.messages.length > 0) {
        userInput = body.messages[body.messages.length - 1].content || "";
    } else {
        r.error("Guardrail: No valid messages found in request body");
        r.return(400, JSON.stringify({ error: "No valid messages in request body" }));
        return;
    }

    debugLog("Guardrail: User input: " + userInput);

    // 检查客户端 Authorization（透传给 LLM）
    let clientAuthHeader = r.headersIn.Authorization;
    if (!clientAuthHeader || !clientAuthHeader.startsWith("Bearer ")) {
        r.error("Guardrail: Missing or invalid Authorization header from client");
        r.return(401, JSON.stringify({ error: "Authorization header with Bearer token required" }));
        return;
    }

    // 扫描开关（仅请求侧）
    let enableRequestScan = r.variables.enable_request_scan === "1";
    debugLog("Guardrail: Request scan enabled: " + enableRequestScan);

    // 如果不开启请求扫描，直接放行
    if (!enableRequestScan) {
        debugLog("Guardrail: Request scan disabled, passing through");
        return;
    }

    // 构造 OpenAI 兼容错误响应
    function buildErrorResponse(reason, model) {
        let id = "chatcmpl-error-" + Math.random().toString(36).substr(2, 9);
        let created = Math.floor(Date.now() / 1000);
        return {
            id: id,
            object: "chat.completion",
            created: created,
            model: model || "f5-ai-guardrails-model",
            choices: [
                {
                    index: 0,
                    message: {
                        role: "assistant",
                        content: reason
                    },
                    finish_reason: "stop",
                    tool_calls: []
                }
            ]
        };
    }

    // 请求侧扫描函数（注意：这里只 scan 请求，不动响应）
    function scanWithAIGR(input, callback) {
        let payload = { input: input };
        debugLog("Guardrail: Sending to AIGR API (request scan): " + JSON.stringify(payload));

        let aigrAuthHeader = r.variables.aigr_api_token;
        if (!aigrAuthHeader) {
            r.error("Guardrail: AIGR API token not configured ($aigr_api_token)");
            r.return(500, JSON.stringify({ error: "Internal server error: AIGR API token missing" }));
            return;
        }

        let aigrHeaders = {
            "Authorization": aigrAuthHeader,
            "Content-Type": "application/json"
        };

        debugLog("Guardrail: AIGR API request headers: " + JSON.stringify(aigrHeaders));

        r.subrequest("/aigr_scan", {
            method: "POST",
            body: JSON.stringify(payload),
            headers: aigrHeaders
        }, function (res) {
            let upstreamAddr = r.variables.upstream_addr || "not available";
            debugLog("Guardrail: AIGR API response status: " + res.status +
                     ", size: " + (res.responseText ? res.responseText.length : 0) +
                     " bytes, upstream: " + upstreamAddr);
            debugLog("Guardrail: AIGR API full response: " +
                     (res.responseText ? res.responseText : "No response text"));

            if (res.status != 200) {
                r.error("Guardrail: AIGR API request failed, status: " + res.status +
                        ", upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse(
                    "External API request failed for request scan (status " + res.status + ")",
                    body.model
                );
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            if (res.responseText.length > 262144) { // 256KB limit
                r.error("Guardrail: AIGR API response too large: " +
                        res.responseText.length + " bytes, upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse(
                    "External API response too large for request scan",
                    body.model
                );
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            let aigrResponse;
            try {
                aigrResponse = JSON.parse(res.responseText);
                debugLog("Guardrail: AIGR parsed result: " + JSON.stringify(aigrResponse.result));
                r.log("Guardrail: AIGR API parsed, outcome: " +
                      (aigrResponse.result && aigrResponse.result.outcome) +
                      ", upstream: " + upstreamAddr);
            } catch (e) {
                r.error("Guardrail: Failed to parse AIGR API response: " + e +
                        ", upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse(
                    "Invalid response from external API for request scan",
                    body.model
                );
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            let outcome = aigrResponse.result && aigrResponse.result.outcome;

            if (outcome === "flagged") {
                // 直接拒绝，构造 OpenAI 风格错误
                let reason = "Request blocked by F5 AI Guardrails";
                if (aigrResponse.result.scannerResults) {
                    let failedScanner = aigrResponse.result.scannerResults.find(
                        scanner => scanner.outcome === "failed"
                    );
                    if (failedScanner &&
                        failedScanner.data &&
                        failedScanner.data.matches &&
                        failedScanner.data.matches.length > 0) {
                        reason = "Request blocked due to sensitive data detected at positions: " +
                                 JSON.stringify(failedScanner.data.matches);
                    }
                }
                let openAiResponse = buildErrorResponse(reason, body.model);
                r.return(200, JSON.stringify(openAiResponse));
            } else if (outcome === "cleared") {
                // 通过，直接放行请求（不改 body）
                callback();
            } else if (outcome === "redacted") {
                // 需要用 redactedInput 替换最后一条 message 的 content，然后再放行
                let redactedValue = aigrResponse.redactedInput;
                if (redactedValue === undefined || redactedValue === null) {
                    redactedValue = (aigrResponse.result && aigrResponse.result.response) || "";
                }

                if (redactedValue !== undefined && redactedValue !== null && redactedValue !== "") {
                    let modifiedBody;
                    try {
                        modifiedBody = JSON.parse(r.requestText);
                    } catch (parseErr) {
                        r.error("Guardrail: Failed to re-parse request body for redacted replacement: " + parseErr);
                        // 回退为原始请求继续
                        callback();
                        return;
                    }

                    if (modifiedBody.messages &&
                        Array.isArray(modifiedBody.messages) &&
                        modifiedBody.messages.length > 0) {
                        modifiedBody.messages[modifiedBody.messages.length - 1].content = redactedValue;
                        let modifiedBodyStr = JSON.stringify(modifiedBody);
                        debugLog("Guardrail: Request redacted, using redactedInput for last message content");

                        // 这里的关键：把“已脱敏的 body”存入变量，交给后续 proxy 使用
                        // 需要在 nginx.conf 中定义：    set $guardrail_redacted_body "";
                        r.variables.guardrail_redacted_body = modifiedBodyStr;

                        callback();
                        return;
                    }
                }

                r.log("Guardrail: Outcome redacted but redactedInput missing/empty, forwarding original request");
                callback();
            } else {
                r.error("Guardrail: Unexpected AIGR API outcome: " + outcome +
                        ", upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse(
                    "Unexpected response from external API for request scan",
                    body.model
                );
                r.return(200, JSON.stringify(openAiResponse));
            }
        });
    }

    // 主流程：只做请求扫描，不处理响应
    scanWithAIGR(userInput, function () {
        // 通过（或已脱敏）后，不要在这里 proxy，不要 touch 响应
        // js_access handler 只需 return 即可让 NGINX 继续执行后续指令（如 proxy_pass）
        debugLog("Guardrail: Request allowed, continuing to upstream");
        return;
    });
}

export default { requestGuard };
