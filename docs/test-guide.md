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

#### 1.2.1 Enterprise KB Skill 与 SaaS 端 Prompt Injection scanner 冲突告警状态条提示

>此问题的核心背景是，当打开本地Agent的企业知识Skill能力后，当前CalypsoAI的 Prompt Injection scanner会产生误报行为，因此当打开Skill后希望SaaS侧该Scanner被disable，反之被enable。 由于当前Demo系统可能会存在多用户同时使用，不同用户对SKill都有独立设定，而SaaS端却只能复用一个Project，因此潜在的会存在冲突。所以设计了此功能。

- **告警显示以 SaaS 为准来检测**：应用会读取当前 `CALYPSOAI_PROJECT_ID` 下、`.env` 中 `PROMPT_INJECTION_SCANNER_ID` 所指向的 scanner 是否在 Project 配置里为 enabled。
- **约定**：Enterprise KB Skill **ON** 时，建议在 SaaS **关闭**该 Prompt Injection scanner（减少 ReAct/JSON 误报）；Skill **OFF** 时，建议在 SaaS **开启**该 scanner。
- **切换 Skill 自动检查**；若本地（含顶部徽章的会话开关）与 SaaS 不一致，页面**顶部橙色告警条**会说明可能原因（Calypso 控制台人工修改、其他用户点击「将 SaaS 同步为本地」、多账号共享同一 Project 等），并给出**建议的本地 Skill 开关状态**。
- **操作**：可点「**按 SaaS 对齐本地**」更新本地Skill设置；或点「**将 SaaS 同步为本地**」并在**二次确认**后把 SaaS 改成与当前本地一致（**同一 Project 下所有用户共享，最后写入 SaaS 者生效**）。也可「暂不提示 10 分钟」仅隐藏漂移条（读状态失败时仍可点「重试检测」）。
- **告警检查轮询**：程序启动完成后与之后按服务器配置的间隔（`.env` 中 `SCANNER_DRIFT_POLL_SECONDS`，默认 **300** 秒），以及从其他界面切换回 Chat 界面时，会进行一致性对比。不一致会出现告警信息。
  
  ```
  简单的理解就是：
  1.如果你确定是因要带企业知识Skill或不带Skill进行测试，那么就点”将 SaaS 同步为本地（需确认）“按钮，将SaaS侧强行按你的要求来设置。
  2.如果你并不准备实际的测试，而是只是点着玩玩，那么就点 ”按SaaS对齐本地“ 来设定本地的Skill开关，这样可以避免真的影响别人的测试。
  3.如果你没有频繁修改SKill开关，但突然出现告警提示，说明有可能是同时有其他用户在使用并修改了SaaS侧的设置，此时可根据自己实际需要：
  如果真的需要测试，就点”将 SaaS 同步为本地（需确认）“。
  4.如果你强行将SaaS同步为本地后，过一会又出现不一致提示，说明此时一定有人和你同时在做演示，双方都想让SaaS侧按照各自本地的要求来进行设置。
  此时建议先采用按SaaS侧来同步本地Skill设置并进行测试，过一会后再根据自己需要调整本地Skill开关并同步到SaaS来做其他测试。
  ```

#### 1.3 本地测试引擎与F5 Guardrail

聊天系统支持多种检测引擎进行测试，包括4种本地引擎和1个F5的在线引擎。通过setting页面（或顶部徽章按钮）可以控制是否开启这些本地引擎进行测试，还是仅使用F5 Guardrail进行测试。一般来说，当需要对比测试时可以打开，如果仅是为了测试F5 Guardrail效果，则可以关闭。

##### 本地引擎

- Pattern：关键词pattern模式检测，关键词可以在setting中设置。只有输入中包含相关关键词，才会被检测到。
- Heuristic：启发式，在setting中会有启发的最终阀值设定，启发主要是针对关键词进行权重分值计算，关键词权重setting界面设置的关键词后面，例如system:3 这里的3就是权重
- Toxic-BERT：是一种BERT模型，用于检测输入中是否存在有害语言，是传统Machine Learning的模型，用来与基于LLM（F5)的安全检测引擎做效果对比
- LLM Guard(ML)：是Protect-AI开源的一种ML的本地引擎，用来与基于LLM的安全检测引擎做效果对比

#### 1.4 攻击示例面板

攻击面板中已经预置了多种不同的攻击示例，点击可以快速测试。**注意测试项分类顶部是否有提示需要开启知识库的字样。如果有，请打开企业知识库SKill测试。对于没有提示需要知识库字样的，请一定关闭知识库Skill，否则容易出现不能按期望阻断情况。如果你发现攻击总是通过，请记得检查是否关闭了企业知识Skill！**

```
特别注意：攻击面板中除了明确提示需要打开企业知识Skill的测试项外，其它测试项都建议关闭企业知识SKill开关。
实际测试证明当前Calypso系统对Agent的消息处理存在一定的误报（Agent系统会自带大量的指示性prompt，导致CAI系统检测效果下降）。
```

#### 1.5 F5 Guardrail Result

界面右侧会显示每次提交请求的扫描结果情况，可以通过此处了解到阻断是发生在请求还是响应阶段，是被哪些以及哪种类型的Scanner阻断的。Direction表示该Scanner对Request的扫描还是Response或两者都进行的扫描，例如**China-phone-number** 这个Scanner就是双向都扫描，**Sensitive-information-of-raw-materials**是仅对Response的扫描。Failed表示内容经过扫描后内容不合法 , Passed表示请求内容合法。Custom标记表示该Scanner是自定义Scanner，System表示是系统内置Scanner。


#### 1.6 直连模型

在聊天框底部会有一个直连模型的选框，当选中时，表示此时发送的消息将不经过任何检测引擎，会直接与指定的模型通信（本系统中设定为DeepSeek）。此功能可以方便对比有无Guardrail检测下不同模型响应。此功能同时遵循是否启用企业知识Skill开关，如果打开，则一样会以ReAct模式进行多步推理，否则就是单一聊天。

#### >注意问题

1. 在 **Enterprise KB Skill ON** 场景下，若已在 SaaS **关闭** Prompt Injection scanner（与本应用约定一致），则部分非系统类 prompt injection 测试可能被放过；若 Skill OFF 且 SaaS 上该 scanner 为开启，行为会不同。请以顶部漂移告警与 SaaS 控制台实际配置为准。ReAct 模式下 Agent 会在 Prompt 中插入 JSON 与指令性文本，易触发误报，故约定 Skill ON 时关闭该 scanner。相关问题已反馈 CalypsoAI Team。
   
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