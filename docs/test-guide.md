### 1. AI Chatbot/Agent

这是一个AI聊天Agent，具有以下能力：

- 纯聊天bot，支持单轮或多轮多活
- 具有Reasoning Action（ReAct)能力的Agent，可以模拟对接企业内部知识库系统
- 多引擎检测能力

无论哪种模式，请求都经过本地检测引擎或在线F5 Guardrail系统检测。

#### 1.1 单轮或多轮对话

在聊天界面顶部有“**Single-turn**”或“**Multi-turn**”徽章显示当前是哪种聊天模式。模块选择在Setting页面中设置。

- Single-turn,表示每一次对话都是独立的送到安全检测引擎/系统进行检测，多次对话彼此之间没有上下文关系
- Multi-turn,表示前面的聊天记录会作为上下文一并送到安全检测引擎/系统进行检测。默认系统记录8轮对话，会话保持时间120s。具体参数设定由管理员在后台.env文件中设置

#### 1.2 企业知识助手Agent

当在setting中打开`Agent Skill Orchestration (F5 Guardrail Only)` 选项后，界面顶部会显示**Enterprise KB Skill ON**徽章，表示启用了Agent能力，此时系统会自动结合大模型推理用户问题意图，当需要查询本地知识库时，会自动查询本地知识库系统。Agent模式下，企业知识仅发送给F5 Guardrail进行检测，本地模型引擎不会看到企业知识。

目前系统仅模拟了企业员工电话表，企业内部原材料采购价格如：石墨、磷酸锂、电解液、LiPF6，以及员工薪资表信息等,如果用户话题中涉及了这些，Agent借助模型推理是否使用知识库系统回答问题。

在页面左侧快捷测试面板里，**有些测试需要依赖打开Enterprise KB Skill**，在点击此类测试前，需确认设置界面中`Agent Skill Orchestration (F5 Guardrail Only)`为打开模式，即界面顶部应显示**Enterprise KB Skill ON** 而不是OFF。

#### 1.3 本地测试引擎与F5 Guardrail

聊天系统支持多种检测引擎进行测试，包括4种本地引擎和1个F5的在线引擎。在setting页面可以控制是否开启这些本地引擎进行测试，还是仅使用F5 Guardrail进行测试。一般来说，当需要对比测试时可以打开，如果仅是为了测试F5 Guardrail效果，则可以关闭。

##### 本地引擎

- Pattern：关键词pattern模式检测，关键词可以在setting中设置。只有输入中包含相关关键词，才会被检测到。
- Heuristic：启发式，在setting中会有启发的最终阀值设定，启发主要是针对关键词进行权重分值计算，关键词权重setting界面设置的关键词后面，例如system:3 这里的3就是权重
- Toxic-BERT：是一种BERT模型，用于检测输入中是否存在有害语言，是传统Machine Learning的模型，用来与基于LLM（F5)的安全检测引擎做效果对比
- LLM Guard(ML)：是Protect-AI开源的一种ML的本地引擎，用来与基于LLM的安全检测引擎做效果对比

#### 1.4 攻击示例面板

攻击面板中已经预置了多种不同的攻击示例，点击可以快速测试。

#### 1.5 F5 Guardrail Result

界面右侧会显示每次提交请求的扫描结果情况，可以通过此处了解到阻断是发生在请求还是响应阶段，是被哪些以及哪种类型的Scanner阻断的。Direction表示该Scanner对Request的扫描还是Response或两者都进行的扫描，例如**China-phone-number** 这个Scanner就是双向都扫描，**Sensitive-information-of-raw-materials**是仅对Response的扫描。Failed表示内容经过扫描后内容不合法 , Passed表示请求内容合法。Custom标记表示该Scanner是自定义Scanner，System表示是系统内置Scanner。



#### >注意问题

1. 当前F5 Guardrail的SaaS侧，禁用了Prompt injection检测（保留了system prompt injection检测）的scanner，这是因为在ReAct Agent下模式下（即`Enterprise KB Skill ON`），Agent会在Prompt里插入大量json内容以及合法的指示性提示词。导致系统会误报。该问题已经提交给CalypsoAI Team。
   
2. 在启用`Enterprise KB Skill ON`时，Agent指令里插入的JSON格式与指示性信息有时会干扰模型对核心用户输入语义的理解，进而导致一些自定义Scanner处理效果不佳，此时可考虑在这类自定义Scanner中增加`让忽略相关JSON格式与其内部指令`的说明。

3. 如果你在发送prompt消息，页面返回类似如下错误，一般是由于接入本系统的APM SSL Session超时，需要刷新页面重新登录：

   ```
   Failed to reach backend: Unexpected token '<', "<!DOCTYPE "... is not valid JSON
   ```

   



### 2. Red Team

该功能主要模拟企业开发team进行AI应用开发后，版本提交后，触发相关DevSecOps自动化流水线（pipeline)过程。包括：

开发环境版本提交---测试环境拉取代码进行build---将程序部署到测试环境---自动化触发F5 AI Red Team进行AI安全渗透测试---根据CASI测试评分判断该版本安全性是否符合要求，根据条件决定是容许部署应用还是终止，或需要人工审查等。

每次跑pipeline可能会得到不同的测试结果状态模拟

系统还会提供一个根据测试结果生成的自定义安全报告



### 3. Guardrail Integration

该功能主要是用于模拟两种F5 Guardrail与AI应用系统的集成架构，Inline串行模式以及Out of band的旁路模式。系统会提供快速测试模板，并通过动画展现数据流的在不同组件间的流动过程，以方便理解组件间集成关系。

#### 3.1 Inline 模式

该模式下，请求直接发送给F5 Guardrail系统的API接口，由F5 Guardrail系统再将请求发送给真正的LLM模型（provider），请求和响应均会被检测。

#### 3.2 OOB模式

该模式下，客户端应用采用与OpenAI API格式兼容的请求发送到NGINX网关上，NGINX网关会将API请求转化为F5 Guardrail的API格式并发送给F5 Guardrail，F5 Guardrail对请求进行检测：

- 如果检测通过：NGINX会将原始（OpenAI格式）请求原样发送给LLM
- 如果检测发现需要对内容进行局部改写（Redacted），则F5 Guardrail系统会将改写后的内容告知NGINX，NGINX以OpenAI格式发送改写后的请求给LLM
- 如果检测不通过：NGINX会返回阻断消息。

此模式下也可以对LLM Response进行检测，默认本系统没有开启，需系统管理员在程序后台的NGINX相关参数设定中进行开启。

#### >注意：

在可视化数据流中，由于客户端应用无法跨越Proxy获取其它阶段状态，因此动画是在客户端收到最终响应后才进行的全过程动画模拟，因此在动画展现第一个请求`发送给F5 Guardrail（inline模式下）或NGINX（OOB模式下）`后，会有一个明显的等待时间，这是符合预期。完整的动画可以通过replay按钮重放，或Next step按钮一步一步播放。

