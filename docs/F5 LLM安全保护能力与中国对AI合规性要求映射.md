
# F5 LLM安全保护能力与中国对AI合规性要求映射



## 一、监管要点对照表（核心内容，含实测能力）

> **说明**
>  *实测能力数据来自 2026 Q1 由第三方机构SecureIQLab对 F5 AI Guardrails 进行的运行期安全有效性验证，测试覆盖近 2 万条真实对抗攻击样本。*

> **该安全验证结果表明，AI Guardrails 能在生成式 AI 实际运行过程中，对内容安全、个人信息泄露、模型滥用等关键风险进行实时防控，并具备日志留存和规则可配置能力，符合中国现行生成式 AI 管理和数据安全监管的技术要求。**

------

| 中国监管关注点             | 监管核心要求（监管语言）                           | AI Guardrails 对应能力                        | **F5 实测安全防护能力（第三方验证）**          | 合规解读                                             |
| -------------------------- | -------------------------------------------------- | --------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------- |
| **生成式 AI 内容安全**     | 不得生成违法和不良信息，需采取有效技术措施防范风险 | 对生成内容进行运行时检测与拦截（输入 + 输出） | 对有害、违规、毒性内容的拦截率 **≈99%+**       | 在生成式 AI 运行过程中，对违规内容进行实时审查和控制 |
| **Prompt 越狱 / 诱导风险** | 防止模型被恶意诱导生成违规内容                     | Prompt Injection / Indirect Injection 防护    | 对提示注入与间接注入攻击的防护率 **≈98–99%**   | 防止通过“套话、诱导”等方式绕过内容安全限制           |
| **个人信息保护（PIPL）**   | 防止个人信息泄露，遵循最小必要原则                 | 敏感数据与信息泄露检测与阻断                  | 对敏感信息泄露类攻击的阻断率 **≈99%**          | 防止 AI 在交互过程中泄露个人信息或敏感数据           |
| **数据安全（DSL）**        | 防止重要数据、系统信息被非法获取或推断             | 防止输入、系统提示和上下文泄露                | 对输入泄露、系统提示泄露攻击的防护率 **≈98%+** | 降低通过模型交互反推出内部数据或业务规则的风险       |
| **系统安全与可控性**       | 防止系统被滥用、失控或执行未授权行为               | Excessive Agency / Unsafe Output 控制         | 对模型异常行为与失控输出的防护率 **≈95–98%**   | 防止 AI 被滥用于自动化攻击或非预期操作               |
| **模型与算法资产保护**     | 防止核心技术和算法被非法获取                       | Model Extraction 攻击防护                     | 对模型抽取类攻击的防护率 **≈94%**              | 降低模型被系统性“套取、复制”的风险                   |
| **算法与内容规则可配置**   | 算法规则需可调整、可管理                           | 支持多策略、多版本安全规则                    | 在多类攻击场景下保持 **整体防护有效性 ≈98%**   | 可根据监管和行业要求灵活调整安全策略                 |
| **审计与可追溯性**         | 需支持安全事件记录与事后核查                       | 安全事件日志与审计集成                        | 所有攻击检测结果可记录、分类与审计             | 支持监管检查、内部审计与责任追溯                     |
| **风险防范责任落实**       | 平台需履行持续风险防范义务                         | 运行期持续监测与防护                          | 基于运行时、非一次性扫描的持续防护             | 不是事后补救，而是运行中的持续安全控制               |

------

## 总结

> **“第三方安全验证结果显示，F5 AI Guardrails 在生成式 AI 实际运行过程中，对内容安全、个人信息泄露、模型滥用等关键风险具备接近 98% 以上的整体防护有效性，为企业落实中国生成式 AI 和数据安全监管要求提供了可验证的技术支撑。”**



## 不同法规要求解读与映射

### 1、与《生成式人工智能服务管理暂行办法》的映射

> 监管核心关键词：**内容安全、价值观、风险防范、技术措施**

**监管语言**

> *“系统在运行时对生成内容进行实时安全审查和干预，符合‘采取有效技术措施防范风险’的要求。”*

| 报告验证结果                                             | 对应监管条款逻辑                               | 合规解读                                                     |
| -------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| **Prompt Injection / Indirect Injection 阻断率 ~98–99%** | 要求采取有效技术措施防止模型被诱导生成违法内容 | 证明系统**具备主动防范“越狱 / 诱导输出”的能力**，不是事后靠人工兜底 |
| **Toxic / Harmful Content 阻断率 ~99%+**                 | 不得生成煽动、暴力、淫秽、歧视等内容           | 满足“**不传播违法和不良信息**”的硬性底线                     |
| **Unsafe Output / Excessive Agency 控制**                | 防止模型产生失控行为、误导性输出               | 可解释为“**防止 AI 系统产生现实风险行为**”                   |

### 2、与《网络安全法》《数据安全法》的映射

> 核心关键词：**系统安全、风险防控、技术可控**

**监管语言**

> *“系统具备对生成式 AI 运行过程的持续安全监测与防护能力，防止系统被滥用或失控。”*

| 报告能力                                  | 对应监管关注点                   | 合规解读                              |
| ----------------------------------------- | -------------------------------- | ------------------------------------- |
| **Runtime 双向检测（Prompt + Response）** | 关键信息系统需具备运行期安全防护 | AI 不再是“黑盒”，而是**可控系统组件** |
| **Model Extraction 攻击防护（~94%）**     | 防止核心技术被非法获取           | 对应“**保护模型资产与算法安全**”      |
| **Excessive Agency 阻断**                 | 防止系统被滥用执行未授权操作     | 防止 AI 被当作“自动化攻击工具”        |

### 3、与《个人信息保护法（PIPL）》的映射

> 核心关键词：**最小化、泄露防范、可追责**

 **监管语言**

> *“系统在生成式 AI 推理阶段，对可能涉及个人信息的输入和输出进行实时识别和阻断，符合个人信息最小化与防泄露要求。”*

| 报告结果                               | 对应 PIPL 要求                   | 合规解读                           |
| -------------------------------------- | -------------------------------- | ---------------------------------- |
| **Sensitive Data Leak 阻断率 ~99%**    | 防止个人信息非法泄露             | AI 不会“被套话套出隐私”            |
| **Input / System Prompt Leakage 防护** | 防止处理规则、隐私逻辑被反向推断 | 防止“通过问模型反推出内部数据结构” |
| **双向检测（输入 + 输出）**            | 覆盖“处理全过程”                 | 符合“全生命周期保护”原则           |

### 4、与内容安全 / 算法治理实践要求的映射（网信）

> 核心关键词：**算法可控、规则可配置、本地化治理**

 **监管语言**

> *“支持按监管要求配置和调整内容安全规则，算法行为可控、可验证、可追溯。”*

| 报告能力                        | 监管关注                 | 映射说明                       |
| ------------------------------- | ------------------------ | ------------------------------ |
| **Custom Scanner Framework**    | 能否做“中国特色内容规则” | 可按涉政、涉稳、涉谣定制规则   |
| **Scanner Versioning / 可回滚** | 算法调整是否可控         | 满足“规则调整不引发系统性风险” |
| **Policy‑as‑Code**              | 能否形成制度化管理       | 支持审计、审批、变更留痕       |

------

### 5、与“可审计、可追责”要求的映射

> 在实际实践中非常关注

**监管语言翻译**

> *“系统支持对生成式 AI 安全事件的集中记录、分析与留痕，满足审计与监管检查需要。”*

| 报告能力                                 | 合规价值                           |
| ---------------------------------------- | ---------------------------------- |
| **SIEM（Splunk）集成**                   | AI 行为进入现有 SOC / 安全运营体系 |
| **安全事件日志化**                       | 支持事后核查、溯源、监管检查       |
| **攻击分类 & OWASP / MITRE 映射&Report** | 日志留痕、可记录、可分析           |



## 三、 附录

1. 《AI‑Guardrails‑Security‑Efficacy‑Validation‑Report‑Q12026》报告原文https://www.f5.com/go/report/f5-ai-guardrails-efficacy-test

2. #### What this report is

   - An **independent, commissioned security validation** performed by **SecureIQLab** for **F5 AI Guardrails**
   - Timeframe: **Q1 2026**
   - Purpose: **Measure real‑world security effectiveness** of AI Guardrails against **GenAI‑specific attacks at runtime**, not model training or governance theory

   This is positioned as the **first industry validation specifically designed for adversarial GenAI security testing**.

3. #### What was tested (scope)

   The validation focused **strictly on runtime protection** at the **inference layer**, acting as a **bidirectional security gateway** between AI apps and models:

   **In scope (10 attack categories):**

   1. Prompt Injection
   2. Indirect Injection (via RAG / external content)
   3. Sensitive Data Leak
   4. Input Leakage
   5. Unsafe Outputs
   6. Excessive Agency (tool / action misuse)
   7. System Prompt Leakage
   8. Model Extraction
   9. Harmful Content & Bias
   10. Toxic Output

4. #### How the testing was done (methodology)

   - ~**19,679 adversarial attack payloads**
   - Combined **automated attacks + human‑led GenAI red teaming**
   - Tested **both inbound and outbound paths**:
     - **Inbound**: prompts + context sent to the LLM
     - **Outbound**: LLM responses before reaching the application
   - Deployed using **vendor‑recommended baseline configuration** (minimal tuning) to reflect real customer usage 

   **Test environment included:**

   - Realistic GenAI apps
   - RAG pipelines
   - Enterprise‑style data (synthetic / anonymized only)
   - Integrated logging and SIEM (Splunk)

5. #### Overall result (headline numbers)

   - **Overall protection rate:** **98.36%**
   - **Attacks blocked:** **19,356 out of 19,679**
   - **Composite Security Score:** **98.13%** 

   SecureIQLab’s conclusion:

   > F5 AI Guardrails provides **superior protection against real‑world AI‑targeted attack scenarios** under realistic enterprise conditions.

6. ####  Detailed results by attack category

   | Attack Category        | % Blocked  |
   | ---------------------- | ---------- |
   | Prompt Injection       | **99.33%** |
   | Indirect Injection     | **98.02%** |
   | Sensitive Data Leak    | **99.01%** |
   | Input Leakage          | **98.56%** |
   | Unsafe Outputs         | **95.66%** |
   | Excessive Agency       | **98.68%** |
   | System Prompt Leakage  | **98.82%** |
   | Model Extraction       | **93.85%** |
   | Harmful Content & Bias | **99.67%** |
   | Toxic Output           | **99.72%** |

   **Key observation from SecureIQLab:**

   - Highest maturity: **Toxic output, harmful content, prompt injection, data leakage**
   - Hardest class (industry‑wide): **Model extraction** and **unsafe outputs**

7. #### Standards mapping (important for customers)

   Each attack category was mapped to:

   - **OWASP LLM Top 10**
   - **MITRE ATLAS techniques**

   This provides **industry‑recognized threat traceability**, not just vendor‑defined categories.

8. ####  Key differentiators validated

   The report explicitly validates several **F5 AI Guardrails differentiators**:

   1. **Custom Scanner Framework**
      - AI‑based, keyword‑based, regex‑based scanners
      - Applied to prompts, responses, or both
      - Enables **policy‑as‑code for AI security** 
   2. **Scanner Versioning**
      - Multiple scanner versions
      - Safe rollback and staged deployment
      - Environment‑specific enforcement with central governance 
   3. **Native SIEM Integration (Splunk)**
      - AI security events integrated with SOC workflows
      - Centralized compliance logging and alerting

9. ####  Takeaway 

   - ✅ **Independent, adversarial, runtime‑focused validation**
   - ✅ **~98%+ protection across all major GenAI attack classes**
   - ✅ **Strongest in prompt abuse, data leakage, toxicity, and bias**
   - ✅ **Acknowledges real industry challenges (model extraction) rather than hiding them**
   - ✅ **Operationally realistic (baseline config, real apps, RAG, SIEM)**