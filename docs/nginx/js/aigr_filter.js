function filterChatCompletion(r) {
    // Check debug toggle
    let debugEnabled = r.variables.enable_debug_logs === "1";

    // Conditional logging function
    function debugLog(message) {
        if (debugEnabled) {
            r.log(message);
        }
    }

    // Parse the incoming request body
    let body;
    try {
        body = JSON.parse(r.requestText);
    } catch (e) {
        r.error("Failed to parse request body: " + e);
        r.return(400, JSON.stringify({ error: "Invalid JSON in request body" }));
        return;
    }

    // Extract the user input from the messages array (last message content)
    let userInput = "";
    if (body.messages && Array.isArray(body.messages) && body.messages.length > 0) {
        userInput = body.messages[body.messages.length - 1].content || "";
    } else {
        r.error("No valid messages found in request body");
        r.return(400, JSON.stringify({ error: "No valid messages in request body" }));
        return;
    }

    // Log input for debugging
    debugLog("User input: " + userInput);

    // Get the Authorization header from the client for llm_provider
    let clientAuthHeader = r.headersIn.Authorization;
    if (!clientAuthHeader || !clientAuthHeader.startsWith("Bearer ")) {
        r.error("Missing or invalid Authorization header");
        r.return(401, JSON.stringify({ error: "Authorization header with Bearer token required" }));
        return;
    }

    // Get scan toggle variables
    let enableRequestScan = r.variables.enable_request_scan === "1";
    let enableResponseScan = r.variables.enable_response_scan === "1";
    debugLog("Request scan enabled: " + enableRequestScan + ", Response scan enabled: " + enableResponseScan);

    // Helper to build OpenAI-compatible error responses
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

    // Function to send request to AIGR API
    function scanWithAIGR(input, scanType, callback) {
        let payload = { input: input };
        debugLog("Sending to AIGR API (" + scanType + " scan): " + JSON.stringify(payload));

        let aigrAuthHeader = r.variables.aigr_api_token;
        if (!aigrAuthHeader) {
            r.error("AIGR API token not configured in NGINX variable $aigr_api_token");
            r.return(500, JSON.stringify({ error: "Internal server error: AIGR API token missing" }));
            return;
        }

        let aigrHeaders = {
            "Authorization": aigrAuthHeader,
            "Content-Type": "application/json"
        };

        debugLog("AIGR API request headers (" + scanType + " scan): " + JSON.stringify(aigrHeaders));

        r.subrequest("/aigr_scan", {
            method: "POST",
            body: JSON.stringify(payload),
            headers: aigrHeaders
        }, function(res) {
            let upstreamAddr = r.variables.upstream_addr || "not available";
            debugLog("AIGR API response status (" + scanType + " scan): " + res.status + ", size: " + (res.responseText ? res.responseText.length : 0) + " bytes, upstream: " + upstreamAddr);
            debugLog("AIGR API full response (" + scanType + " scan): " + (res.responseText ? res.responseText : "No response text"));

            if (res.status != 200) {
                r.error("AIGR API request failed with status (" + scanType + " scan): " + res.status + ", upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse("External API request failed for " + scanType + " scan (status " + res.status + ")", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            if (res.responseText.length > 262144) { // 256KB limit
                r.error("AIGR API response too large (" + scanType + " scan): " + res.responseText.length + " bytes, upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse("External API response too large for " + scanType + " scan", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            let aigrResponse;
            try {
                aigrResponse = JSON.parse(res.responseText);
                debugLog(aigrResponse.result);
                //debugLog("AIGR API response parsed (" + scanType + " scan), outcome: " + (aigrResponse.result && aigrResponse.result.outcome) + ", upstream: " + upstreamAddr);
                r.log("AIGR API response parsed (" + scanType + " scan), outcome: " + (aigrResponse.result && aigrResponse.result.outcome) + ", upstream: " + upstreamAddr);
            } catch (e) {
                r.error("Failed to parse AIGR API response (" + scanType + " scan): " + e + ", upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse("Invalid response from external API for " + scanType + " scan", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            let outcome = aigrResponse.result && aigrResponse.result.outcome;
            if (outcome === "flagged") {
                let reason = scanType.charAt(0).toUpperCase() + scanType.slice(1) + " blocked by F5 AI Guardrails";
                if (aigrResponse.result.scannerResults) {
                    let failedScanner = aigrResponse.result.scannerResults.find(
                        scanner => scanner.outcome === "failed"
                    );
                    if (failedScanner && failedScanner.data && failedScanner.data.matches && failedScanner.data.matches.length > 0) {
                        reason = scanType.charAt(0).toUpperCase() + scanType.slice(1) + " blocked due to sensitive data detected at positions: " + JSON.stringify(failedScanner.data.matches);
                    }
                }
                let openAiResponse = buildErrorResponse(reason, body.model);
                r.return(200, JSON.stringify(openAiResponse));
            } else if (outcome === "cleared" || outcome === "redacted") {
                //here for redacted response, still send request directly to provider
                //TODO, for redacted response, need send the redacted content to provider
                callback();
            } else {
                r.error("Unexpected AIGR API response outcome (" + scanType + " scan), upstream: " + upstreamAddr);
                let openAiResponse = buildErrorResponse("Unexpected response from external API for " + scanType + " scan", body.model);
                r.return(200, JSON.stringify(openAiResponse));
            }
        });
    }

    // Function to send request to provider and handle response
    function sendToProvider() {
        debugLog("Sending to LLM Provider: " + r.requestText);

        let providerHeaders = {
            "Authorization": clientAuthHeader,
            "Content-Type": "application/json"
        };

        debugLog("LLM Provider request headers: " + JSON.stringify(providerHeaders));

        r.subrequest("/llm_provider", {
            method: "POST",
            body: r.requestText,
            headers: providerHeaders
        }, function(providerRes) {
            let providerUpstreamAddr = r.variables.upstream_addr || "not available";
            debugLog("Provider API response status: " + providerRes.status + ", size: " + (providerRes.responseText ? providerRes.responseText.length : 0) + " bytes, upstream: " + providerUpstreamAddr);
            debugLog("Provider API full response: " + (providerRes.responseText ? providerRes.responseText : "No response text"));

            if (providerRes.status != 200) {
                r.error("Provider API request failed with status: " + providerRes.status + ", upstream: " + providerUpstreamAddr);
                let openAiResponse = buildErrorResponse("Provider API request failed (status " + providerRes.status + ")", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            // If response scan is disabled, return the provider response directly
            if (!enableResponseScan) {
                debugLog("Response scan disabled, returning provider response directly");
                r.return(200, providerRes.responseText);
                return;
            }

            // Parse the provider response to extract the content for scanning
            let providerResponse;
            try {
                providerResponse = JSON.parse(providerRes.responseText);
            } catch (e) {
                r.error("Failed to parse Provider API response: " + e + ", upstream: " + providerUpstreamAddr);
                let openAiResponse = buildErrorResponse("Invalid response from provider API", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            // Extract the content from the provider response (assuming OpenAI-compatible format)
            let providerContent = "";
            if (providerResponse.choices && Array.isArray(providerResponse.choices) && providerResponse.choices.length > 0) {
                providerContent = providerResponse.choices[0].message.content || "";
            } else {
                r.error("No valid content found in Provider API response");
                let openAiResponse = buildErrorResponse("No valid content in provider response", body.model);
                r.return(200, JSON.stringify(openAiResponse));
                return;
            }

            // Scan the provider response with AIGR
            scanWithAIGR(providerContent, "response", function() {
                // If response scan passes, return the provider's response
                r.return(200, providerRes.responseText);
            });
        });
    }

    // Main logic based on scan toggles
    if (!enableRequestScan && !enableResponseScan) {
        // If both scans are disabled, send directly to provider
        debugLog("Both request and response scans disabled, sending directly to provider");
        sendToProvider();
    } else if (!enableRequestScan) {
        // If only response scan is enabled, send directly to provider
        debugLog("Request scan disabled, sending directly to provider");
        sendToProvider();
    } else {
        // If request scan is enabled, scan the request first
        scanWithAIGR(userInput, "request", sendToProvider);
    }
}

// Export the function for NGINX to use
export default { filterChatCompletion };