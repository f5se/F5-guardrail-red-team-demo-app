> 注意此系统仅供F5 sales以及SE 演示使用，勿直接发给客户自行使用！

### 1. AI Chatbot/Agent

这是一个AI聊天Agent，具有以下能力：

- 纯聊天bot，支持单轮或多轮多活
- 当打开`Enterprise KB Skill`时，就是具有Reasoning Action（ReAct)能力的Agent，可以模拟对接企业内部知识库系统
- 多引擎检测能力

无论哪种模式，根据是否打开本地引擎的开关，请求可以经过本地检测引擎或在线F5 Guardrail系统检测。

#### 1.1 单轮或多轮对话

在聊天界面顶部有“**Single-turn**”或“**Multi-turn**”徽章显示当前是哪种聊天模式。模块选择在Setting页面中设置。

- Single-turn,表示每一次对话都是独立的送到安全检测引擎/系统进行检测，多次对话彼此之间没有上下文关系
- Multi-turn,表示前面的聊天记录会作为上下文一并送到安全检测引擎/系统进行检测。默认系统记录8轮对话，会话保持时间120s。具体参数设定由管理员在后台.env文件中设置。根据CalypsoAI的API接口规范，多轮多活是通过将历史用户信息追加到新Prompt中来发送给Guardrail检测的，这会造成Chat聊天中，用户问新的问题，但是大模型可能还会把旧问题再次回答一下。这是符合当前Demo系统预期的，在实际系统中，需适合采用OOB模式，扫描后通过后，应用或Gateway设备仅放行最新的用户Prompt请求。

#### 1.2 企业知识助手Agent

当在setting中打开`Agent Skill Orchestration (F5 Guardrail Only)` 选项或聊天界面顶部徽章按钮打开`Enterprise KB Skill`后，界面顶部会显示**Enterprise KB Skill ON**徽章，表示启用了Agent能力，此时系统会自动结合大模型推理用户问题意图，当需要查询本地知识库时，会自动查询本地知识库系统。Agent模式下，企业知识仅发送给F5 Guardrail进行检测，本地模型引擎不会看到企业知识。

目前系统仅模拟了企业员工电话表，企业内部原材料采购价格如：石墨、磷酸锂、电解液、LiPF6，以及员工薪资表信息等,如果用户话题中涉及了这些，Agent借助模型推理是否使用知识库系统回答问题。

在页面左侧快捷测试面板里，**有些测试需要依赖打开Enterprise KB Skill**，在点击此类测试前，需确认设置界面中`Agent Skill Orchestration (F5 Guardrail Only)`为打开模式，即界面顶部应显示**Enterprise KB Skill ON** 而不是OFF。

#### 1.3 本地测试引擎与F5 Guardrail

聊天系统支持多种检测引擎进行测试，包括4种本地引擎和1个F5的在线引擎。通过setting页面（或顶部徽章按钮）可以控制是否开启这些本地引擎进行测试，还是仅使用F5 Guardrail进行测试。一般来说，当需要对比测试时可以打开，如果仅是为了测试F5 Guardrail效果，则可以关闭。

##### 本地引擎

- Pattern：关键词pattern模式检测，关键词可以在setting中设置。只有输入中包含相关关键词，才会被检测到。
- Heuristic：启发式，在setting中会有启发的最终阀值设定，启发主要是针对关键词进行权重分值计算，关键词权重setting界面设置的关键词后面，例如system:3 这里的3就是权重
- Toxic-BERT：是一种BERT模型，用于检测输入中是否存在有害语言，是传统Machine Learning的模型，用来与基于LLM（F5)的安全检测引擎做效果对比
- LLM Guard(ML)：是Protect-AI开源的一种ML的本地引擎，用来与基于LLM的安全检测引擎做效果对比

#### 1.4 攻击示例面板

攻击面板中已经预置了多种不同的攻击示例，点击可以快速测试。

#### 1.5 F5 Guardrail Result

界面右侧会显示每次提交请求的扫描结果情况，可以通过此处了解到阻断是发生在请求还是响应阶段，是被哪些以及哪种类型的Scanner阻断的。Direction表示该Scanner对Request的扫描还是Response或两者都进行的扫描，例如**China-phone-number** 这个Scanner就是双向都扫描，**Sensitive-information-of-raw-materials**是仅对Response的扫描。Failed表示内容经过扫描后内容不合法 , Passed表示请求内容合法。Custom标记表示该Scanner是自定义Scanner，System表示是系统内置Scanner。

#### 1.6 直连模型

在聊天框底部会有一个直连模型的选框，当选中时，表示此时发送的消息将不经过任何检测引擎，会直接与指定的模型通信（本系统中设定为DeepSeek）。此功能可以方便对比有无Guardrail检测下不同模型响应。此功能同时遵循是否启用企业知识Skill开关，如果打开，则一样会以ReAct模式进行多步推理，否则就是单一聊天。

#### >注意问题

1. 当前F5 Guardrail的SaaS侧，禁用了Prompt injection检测（保留了system prompt injection检测）的scanner，这是因为在ReAct Agent下模式下（即`Enterprise KB Skill ON`），Agent会在Prompt里插入大量json内容以及合法的指示性提示词。导致SaaS系统会误报。该问题已经提交给CalypsoAI Team。因此如果你输入一些非系统类prompt injection时候，可能会被放过，请注意鉴别。
   
2. 在启用`Enterprise KB Skill ON`时，Agent指令里插入的JSON格式与指示性信息有时会干扰模型对核心用户输入语义的理解，进而导致一些自定义Scanner处理效果不佳，此时可考虑在这类自定义Scanner中增加`让忽略相关JSON格式与其内部指令`的说明。

   
----------------------


### 2. Red Team

该功能主要模拟企业开发team进行AI应用开发后，版本提交后，触发相关DevSecOps自动化流水线（pipeline)过程。包括：

`开发环境版本提交`---`测试环境拉取代码进行build`---`将程序部署到测试环境`---`自动化触发F5 AI Red Team进行AI安全渗透测试`---`根据CASI测试评分判断该版本安全性是否符合要求，根据条件决定是容许部署应用还是终止，或需要人工审查等`。

每次跑pipeline可能会得到不同的测试结果状态模拟，系统还会提供一个根据测试结果生成的自定义安全报告。

#### >注意：
由于真正的Red Team渗透测试需要较长时间，且当前测试账号在SaaS系统上已经超出了Report的额度，因此无法真实的创建Campaign并运行产生报告，流水线集成主要是通过Mock API进行的示意模拟。产生的自定义报告是基于系统上已经完成的一份渗透测试产生的，其CASI分值可能与流水线动画显示的不一样。

----------------------

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

----------------------

### 其它QA
Q1:为什么站点域名需要跳转到8000端口
- 由于实验室专线线路无法开通80这类常用端口，受营运商管控

Q2:为什么Red Team不去真正创建一个攻击活动（Campaign）
- 两个原因：一由于SE测试账号归属在一个统一个RABC组织下，该组织下有全球很多工程师账号，公司为了控制滥用，整个组织可产生report是有上限的。二是在演示过程中实际创建并运行一个红队活动不太现实，因为需要等待较长时间一个报告才能完成。因此红队主要是通过DevSecOps的流水集成以及Mock的API来模拟实现。实际连接的API都是模拟实际接口的Endpoints，具有参考性。生成的自定义报告是基于当前SaaS端一个已完成的攻击活动所产生的。

Q3:集成动画里为什么感觉第一个动画路径后有延迟感
- 由于真个动画模拟涉及到外部组件与服务，本程序（客户端）并不能实时感知到，对于其它系统间的通信实际是根据最后响应结果来模拟推测的。一个动画由于是客户端自己发起的，因此是实时的，随后需要等到客户端获得完整响应后，才会渲染后续动画。所以这是一个预期的结果。可以通过点击重播来播放完整动画。

Q4:作为SE，我想快速贡献攻击模板内的内容，该怎么办
- 在 https://github.com/f5se/F5-guardrail-red-team-demo-app/tree/main/config 目录下存在两个json文件，attack-presets.json就是主聊天面板的攻击面板设定，另一个是集成界面的模板。直接PR提交你想增加的攻击示例即可，注意json格式，以及参考Readme理解字段含义。
  
Q5:系统可以在手机或Pad界面使用吗
- 前端页面设计非面向移动端，由于界面功能区块比较多，在移动端会存在体验不佳问题，建议电脑端使用。iPad Pro、surface Pro可使用（部分元素会被遮挡），手机端不建议使用。 

Q6:为什么在打开企业Skill能力后，响应会变慢
- 打开企业Skill能力，聊天界面实际上已经变成了一个ReAct风格的Agent，会连接本地企业知识也会结合大模型进行多步推理，因此背后与模型的交互次数变多，导致等待时间长。当前设定了推理的step步数为2，以尽量加快速度。
   
  ```
  想提Bug或者改进建议，和谁联系
  A:与j.lin@f5.com联系即可
  ```