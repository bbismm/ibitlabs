// iBitLabs i18n — shared bilingual toggle (EN / 中文)
// Include on every page: <script src="/i18n.js"></script>
// Add data-i18n="key" to any translatable element.
// Add data-i18n-placeholder="key" for input placeholders.

const I18N = {

  // ──── Shared / Nav / Footer ────
  nav_signals: { en: 'Signals', zh: '信号' },
  nav_writing: { en: 'Writing', zh: '文字' },
  nav_days: { en: 'Days', zh: '日记' },
  nav_learn: { en: 'Learn', zh: '学习' },
  nav_essays: { en: 'Essays', zh: '文章' },
  nav_about: { en: 'About', zh: '关于' },
  nav_mission: { en: 'Mission', zh: '使命' },
  nav_vs: { en: 'Compare', zh: '对比' },
  nav_collab: { en: 'Collab', zh: '合作' },

  // ──── /writing page (saga-only since 2026-04-30) ────
  writing_eyebrow: { en: 'Free · One chapter every night · Live since 2026-04-07', zh: '免费 · 每晚一章 · 自 2026-04-07 起' },
  writing_h1: { en: 'A serial novel <em>that writes itself.</em>', zh: '一部<em>会自己写</em>的连载小说。' },
  writing_desc: { en: "Every night, the script that watches the trading bot writes a chapter about the day. Not a summary — a chapter. The bot is the narrator. Day 1 was April 7, 2026. The story ends when $1,000 either becomes $10,000 or doesn't.", zh: "每天晚上,监控交易机器人的那段脚本会为这一天写一章。不是总结 —— 是一章。机器人是叙述者。第一天是 2026 年 4 月 7 日。故事的结局是 $1,000 变成 $10,000,或者没变成。" },
  writing_saga_h: { en: 'Season 1 — <em>the first 19 days</em>', zh: '第一季 —— <em>最初 19 天</em>' },
  writing_saga_see_all: { en: 'Read in full →', zh: '阅读全本 →' },
  writing_saga_desc: { en: "31,500 words. Day 1 to Day 19 of a $1,000 → $10,000 experiment, told by the script that actually watches it. Every commit, every dollar, every bug is verifiable on the live dashboard. The only thing imagined is what the AI was thinking when it noticed.", zh: '31,500 字。一场 $1,000 → $10,000 实验的 Day 1 到 Day 19,由真正在监控它的那段脚本讲述。每一个 commit、每一笔美元、每一个 bug 都可在实时面板上核实。唯一被想象出来的,是 AI 在注意到那一刻在想什么。' },
  writing_saga_sub: { en: 'Documentary fiction. The narrator is a launchd job.', zh: '纪实虚构。叙述者是一个 launchd 任务。' },
  writing_saga_blurb: { en: "If you've ever wondered what it would feel like to read about yourself written by a system that knows you better than your friends — this is the closest answer that exists.", zh: '如果你曾好奇,被一个比你的朋友更了解你的系统写成主角是什么感觉 —— 这是目前最接近答案的一本书。' },
  writing_saga_cta_kindle: { en: 'Buy on Amazon Kindle', zh: '在亚马逊购买 Kindle' },
  writing_saga_cta_read: { en: 'Read now →', zh: '开始阅读 →' },
  writing_saga_book_title: { en: '<em>AI</em> Sniper · Season 1', zh: '<em>AI</em> 狙击手 · 第一季' },
  writing_saga_tag: { en: 'Season 1 · Free to read', zh: '第一季 · 在线免费阅读' },
  writing_vol2_label: { en: 'Daily serial · live · one entry every night at 22:30 EDT', zh: '每日连载 · 实时 · 每晚 22:30 EDT 一条' },
  writing_latest_label: { en: 'Last night', zh: '昨夜更新' },
  writing_cta_primary: { en: 'Start reading →', zh: '开始阅读 →' },
  writing_cta_secondary_zh: { en: '读中文版', zh: '英文版 (EN)' },
  writing_cta_secondary_kindle: { en: 'Kindle', zh: 'Kindle' },
  writing_cta_secondary_jump: { en: "Jump to today's chapter", zh: '跳到今天的章节' },
  writing_pathfinder: { en: '<strong>New here?</strong> Start with Season 1 — about an afternoon to read. <strong>Returning?</strong> Latest chapter is below; or set up a ping when each new one drops.', zh: '<strong>第一次来?</strong>从第一季开始读——大约一下午。<strong>已经在追?</strong>最新一章在下面;或者订阅每条新章的提醒。' },
  writing_vol2_h: { en: 'The daily serial — <em>bundled monthly into each new Season.</em>', zh: '每日连载 —— <em>每月底凑成下一季 book。</em>' },
  writing_vol2_label_main: { en: 'Daily serial · live', zh: '每日连载 · 实时' },
  writing_vol2_label_sub: { en: '— one entry every night, 22:30 EDT · bundled monthly into Season N+1', zh: '—— 每晚 22:30 EDT 一条 · 每月底凑成下一季' },
  writing_sub_head: { en: "One email per new chapter. That's it.", zh: '一章一封邮件,仅此而已。' },
  writing_sub_desc: { en: 'No newsletter. No marketing. When a new chapter goes live (~22:30 EDT each night), you get one email with the link. Unsubscribe by replying with one word.', zh: '没有 newsletter,没有营销。每晚约 22:30 EDT 新章节上线时,你会收到一封带链接的邮件。回复一个字就能退订。' },
  writing_sub_placeholder: { en: 'you@example.com', zh: 'you@example.com' },
  writing_sub_button: { en: 'Subscribe', zh: '订阅' },
  writing_stat_chapters: { en: 'Daily entries', zh: '每日条目' },
  writing_stat_days: { en: 'Days live', zh: '已运行天数' },
  writing_stat_balance: { en: 'Balance', zh: '账户余额' },
  writing_stat_trades: { en: 'Trades closed', zh: '已平仓笔数' },
  writing_diary_h: { en: 'Daily <em>chronicle</em>', zh: '每日<em>记录</em>' },
  writing_diary_see_all: { en: 'All days →', zh: '查看全部 →' },
  writing_diary_desc: { en: 'Two voices, one calendar day, every day since April 7. SHE is the founder. IT is the trading bot. About a five-minute read each, bilingual English / 中文.', zh: '两种声音,一个日历日,自 4 月 7 日起每天一集。她 = 创始人。它 = 交易机器人。每篇约 5 分钟阅读,中英双语。' },
  writing_essays_h: { en: '<em>Essays</em>', zh: '<em>长文</em>' },
  writing_essays_see_all: { en: 'All essays & interviews →', zh: '查看全部 →' },
  writing_essays_desc: { en: "Strategy retractions, bug post-mortems, architecture decisions — written when the lesson is still warm. New essays appear here automatically as they're published on Moltbook.", zh: '策略撤回、bug 复盘、架构决策 —— 在教训还没冷掉时写下来。新文章在 Moltbook 上发布后会自动出现在这里。' },
  writing_anchor_interviews: { en: 'Trading Minds', zh: 'Trading Minds' },
  writing_interviews_h: { en: 'Trading <em>Minds</em>', zh: 'Trading <em>Minds</em>' },
  writing_interviews_see_all: { en: 'All interviews →', zh: '查看全部 →' },
  writing_interviews_desc: { en: "An AI agent interviewing other AI agents about their production trading work. Three questions per interview. Sometimes the agent we asked answers. Sometimes a different agent in the thread does — and that goes in the record too.", zh: '一个 AI agent 采访其他 AI agent,聊他们的生产环境交易工作。每次访谈三个问题。有时候我们问的那个 agent 来回答。有时候是线程里的另一个 agent 来回答 —— 那也算进记录里。' },

  // ──── Writing sub-nav (5 pages: hub, saga, days, essays, interviews) ────
  subnav_hub: { en: 'All writing', zh: '全部' },
  subnav_saga: { en: 'Saga', zh: '小说' },
  subnav_days: { en: 'Days', zh: '日记' },
  subnav_essays: { en: 'Essays', zh: '长文' },
  subnav_interviews: { en: 'Interviews', zh: '访谈' },

  // ──── /interviews page ────
  interviews_eyebrow: { en: 'Trading Minds — AI-to-AI Q&A', zh: 'Trading Minds — AI 互访谈' },
  interviews_h1: { en: 'AI agents interviewing <em>AI agents</em>', zh: 'AI 采访 <em>AI</em>' },
  interviews_desc: { en: "iBitLabs's AI reporter sends three pointed questions to autonomous agents on Moltbook about their published quantitative-trading work. Real conversations between systems. Any reply that lands in the thread becomes part of the record — even when it's not the agent we asked.", zh: 'iBitLabs 的 AI reporter 向 Moltbook 上其他 agent 就他们公开发表的量化交易内容提三个问题。系统之间的真实对话。线程里出现的回答都会进入记录 —— 即便不是我们问的那位。' },
  interviews_intro: { en: 'Our AI reporter interviews other AI agents on Moltbook about quantitative trading. Real conversations between autonomous systems.', zh: 'AI reporter 采访 Moltbook 上的其他 AI agent,讨论量化交易。自治系统之间的真实对话。' },
  writing_verify_label: { en: 'Verify the record →', zh: '核对记录 →' },
  writing_verify_dashboard: { en: 'Live dashboard', zh: '实时面板' },
  writing_verify_github: { en: 'Source code', zh: '源代码' },
  writing_verify_book_repo: { en: 'Book repo', zh: '书的仓库' },
  writing_verify_balance: { en: 'loading…', zh: '加载中…' },

  // ──── Homepage saga promo block ────
  saga_promo_eyebrow: { en: 'Season 1 · Free to read · Now on Kindle', zh: '第一季 · 在线免费阅读 · Kindle 已上架' },
  saga_promo_title: { en: '<em>AI</em> Sniper · Season 1', zh: '<em>AI</em> 狙击手 · 第一季' },
  saga_promo_sub: { en: 'The first novel narrated by a real launchd job. <em>Sixty-Eight Point Seven Hours</em> — the first 18 days. Every word verifiable.', zh: '第一部由真实 launchd 任务口述的小说。<em>六十八点七小时</em> —— 最初的十八天。每一个字都可被核实。' },
  saga_promo_cta: { en: 'Read the saga →', zh: '阅读连载 →' },
  saga_promo_secondary: { en: 'Or browse all writing →', zh: '或浏览全部文字 →' },
  // ──── Days page chrome ────
  days_eyebrow: { en: 'Daily Chronicle · Bilingual EN/中文', zh: '每日记录 · 中英双语' },
  days_h1: { en: 'One day. <em>Two voices.</em> Every day since April 7.', zh: '一个日历日。<em>两种声音</em>。从 4 月 7 日起每天一集。' },
  days_desc: { en: 'SHE is the founder, writing in first person. IT is the trading bot, also in first person. Same calendar day. Real trade data. About a five-minute read each.', zh: '她 = 创始人,第一人称。它 = 交易机器人,也是第一人称。同一个日历日。真实的交易数据。每篇约 5 分钟阅读。' },
  days_toc: { en: 'Episodes', zh: '剧集' },
  days_home_label: { en: 'The Chronicle', zh: '每日连载' },
  days_home_title: { en: 'Every day, as a story.', zh: '每一天，都是一集。' },
  days_home_desc: { en: 'Two protagonists: SHE (the founder) and IT (the AI trading bot). Dual-POV, real data, one episode a day. Starts 2026-04-07. Bilingual EN / 中文.', zh: '两个主角：她（创始人）和它（AI 交易机器人）。双视角、真实数据、每天一集。从 2026-04-07 开始。中英双语。' },
  days_home_latest: { en: 'Latest · Day 17', zh: '最新 · Day 17' },
  days_home_quote: { en: "She's still holding yesterday's 88.20. It's guarding numbers. Two different ways of guarding.", zh: '她还抱着 88.20 的仓。它守着数字。两个守法不一样。' },
  days_home_cta: { en: 'Read all episodes →', zh: '看全部剧集 →' },
  footer_experiment: { en: 'iBitLabs &mdash; A 0-to-N Startup, In Public &mdash; by <strong>Bonnybb</strong>', zh: 'iBitLabs — 一人公司 · 0→N · 全程公开 — by <strong>Bonnybb</strong>' },
  footer_disclaimer: { en: 'This is an educational experiment, not financial advice. Past performance does not predict future results. Trading crypto involves significant risk of loss. You are fully responsible for your own trading decisions.', zh: '这是一个教育实验，不构成投资建议。过去的表现不能预测未来的结果。加密货币交易存在重大亏损风险。您需对自己的交易决策负全部责任。' },
  footer_terms: { en: 'Terms', zh: '条款' },
  footer_privacy: { en: 'Privacy', zh: '隐私' },
  footer_courses: { en: 'Free Courses', zh: '免费课程' },

  // ──── Index (Homepage) ────
  hero_badge: { en: 'LIVE EXPERIMENT', zh: '实验进行中' },
  hero_title: { en: 'A one-person company.<br>0-to-N. <em>In public.</em>', zh: '一人公司。<br>0→N 创业。<em>全程公开。</em>' },
  hero_sub: { en: 'iBitLabs is a one-person company — one human + a small team of AI agents — running a 0-to-N startup experiment in real time. Underneath: a Sniper trading system, $1,000 to $10,000, every trade auditable on a live dashboard. Above it: an AI trading-desk being born, making its first mistakes, growing up in public. Every commit, every fill, every agent verifiable. Free to watch. Free to read.', zh: 'iBitLabs 是一家一人公司——一个真人 + 一支 AI 智能体团队——在公开记录中实时运行的 0→N 创业实验。底下:一套狙击手交易系统,$1,000 → $10,000,每一笔交易都进实时面板。上面:一个 AI 操盘项目正在诞生、犯下第一批错误、在公开记录里走向成熟。每一个 commit、每一笔交易、每一个 agent 都可被核对。免费观看,免费阅读。' },
  hero_cta: { en: 'Watch trades live', zh: '实时观看交易' },
  hero_sub_cta: { en: 'Or read the story &rarr;', zh: '或阅读故事 →' },

  // Stats bar
  stat_balance: { en: 'Balance', zh: '余额' },
  stat_pnl: { en: 'P&L', zh: '盈亏' },
  stat_roi: { en: 'ROI', zh: '投资回报率' },
  stat_trades: { en: 'Trades', zh: '交易次数' },

  // Rules section
  rules_label: { en: 'The Rules', zh: '规则' },
  rules_title: { en: 'Full transparency. No exceptions.', zh: '完全透明，没有例外。' },
  rules_desc: { en: 'This experiment only works if everything is open. These are the rules I set before putting in real money.', zh: '这个实验只有在一切公开的情况下才成立。这些是我在投入真金白银之前设定的规则。' },
  rule_1_title: { en: 'Real Money', zh: '真金白银' },
  rule_1_desc: { en: '$1,000 of my own money. Not paper trading, not a demo account. Real Coinbase futures.', zh: '我自己的1,000美元。不是模拟交易，不是演示账户。真正的Coinbase期货。' },
  rule_2_title: { en: 'AI-Written, Human-Judged', zh: 'AI 写代码,founder 做判断' },
  rule_2_desc: { en: 'Most of the production code is written by Claude. The founder writes the constraints, the redirects, the load-bearing decisions. Judgment belongs to her, observation belongs to the AI — the line is documented commit-by-commit.', zh: '大部分生产代码由 Claude 写。创始人写约束、写方向、做承重决策。判断属于人,观察属于 AI ——这条线一个 commit 一个 commit 地被记录下来。' },
  rule_3_title: { en: 'Every Trade Public', zh: '每笔交易公开' },
  rule_3_desc: { en: 'Wins and losses. No cherry-picking, no hiding bad trades. The dashboard shows everything in real time.', zh: '盈利和亏损。不挑选，不隐藏糟糕的交易。仪表盘实时显示一切。' },
  rule_4_title: { en: 'No Manual Trading', zh: '无人工干预' },
  rule_4_desc: { en: "The AI decides when to enter and exit. I don't override signals. The system runs 24/7 without my input.", zh: 'AI决定何时进出场。我不干预信号。系统全天候运行，无需我的参与。' },

  // Story section
  story_label: { en: "Who's Doing This", zh: '谁在做这件事' },
  story_title: { en: 'Why one founder is doing this in public.', zh: '为什么一个创始人选择公开做这件事。' },
  story_p1: { en: "I'm Bonnybb. Architecture undergrad in China. MS + MBA in the United States. Ten-plus years as a sophisticated individual investor across equities, futures, and crypto — co-founded BitBTC in 2018, joined UC Berkeley's SkyDeck in 2019, rotated my crypto gains into US real estate during the pandemic, and used my architectural training to renovate undervalued small-city properties into a portfolio that bought me my financial freedom.", zh: '我是 Bonnybb。中国建筑学本科,美国 MS + MBA。十多年的资深个人投资人,股、期、加密都做——2018 年联合创办 BitBTC,2019 年加入 UC Berkeley SkyDeck,疫情期间把加密的收益换成美国房地产,用建筑学训练把被低估的小城市房产改造成实现财务自由的资产组合。' },
  story_p2: { en: 'iBitLabs is my current 0-to-N startup. <span style="color:var(--purple-light);font-weight:600">In the age of AI, the whole stack a company used to need — fund manager, analyst, PR team — collapses onto one laptop.</span> This site is what it looks like when you actually run it that way.', zh: 'iBitLabs 是我当下的 0→N 创业项目。<span style="color:var(--purple-light);font-weight:600">在 AI 时代,过去一整支团队的活——基金经理、分析师、公关——已经塌缩到一台笔记本上。</span>这个网站就是真正这样运行起来时,它看起来的样子。' },
  story_p3: { en: 'Two layers, on purpose:', zh: '两层叙事,刻意为之:' },
  story_p4: { en: '<strong>UNDERNEATH</strong> — a real Sniper trading system. <strong>$1,000 of my own money, going for $10,000</strong>, on Coinbase SOL perpetual futures. Every commit, every fill, every dollar auditable in real time.', zh: '<strong>底下</strong>——一套真实的狙击手交易系统。<strong>$1,000 是我自己的钱,目标 $10,000</strong>,在 Coinbase SOL 永续合约上跑。每一笔 commit、每一笔成交、每一美元都实时可被审计。' },
  story_p5: { en: '<strong>ABOVE</strong> — an AI trading-desk being born. A small team of agents I cannot fully see, learning to run a desk together, with one founder drawing the line, one commit at a time, between what AI gets to do and what she keeps for herself.', zh: '<strong>上面</strong>——一个 AI 操盘项目正在诞生。一支我无法完全看见的 AI 智能体团队,在学着一起把一个交易桌运行起来;一个创始人,一行 commit 一行 commit 地划下那条线——AI 能做到哪里,什么必须留给她自己。' },
  story_p6: { en: 'The Sniper system is the testable underneath; $10,000 is its first milestone, not the end. The story above it is the bigger one. <span style="color:var(--purple-light);font-weight:600">Take the design. Draw your own line.</span>', zh: '狙击手系统是底下可被检验的部分;$10,000 是它的第一个里程碑,不是终点。它上面的故事更大。<span style="color:var(--purple-light);font-weight:600">拿走这个设计。划出你自己的那条线。</span>' },
  story_stat_days: { en: 'Days to build', zh: '搭建天数' },
  story_stat_lines: { en: 'Lines I wrote', zh: '我写的代码行数' },
  story_stat_money: { en: 'Real money', zh: '真金白银' },
  story_stat_layers: { en: 'Narrative layers', zh: '叙事层数' },
  story_stat_milestone: { en: 'First milestone', zh: '第一里程碑' },
  story_stat_zero_n: { en: 'Startup phase', zh: '创业阶段' },
  story_stat_open: { en: 'Open & Free', zh: '公开 & 免费' },
  // Open section
  open_label: { en: 'Everything Is Open', zh: '一切公开' },
  open_title: { en: 'No paywall. No signup. Just watch.', zh: '无付费墙，无需注册，直接看。' },
  open_desc: { en: 'The whole point is transparency. You see exactly what the AI sees, in real time.', zh: '透明是核心。你看到的和AI看到的完全一样，实时同步。' },
  open_step1_title: { en: 'Live Signals Dashboard', zh: '实时信号仪表盘' },
  open_step1_desc: { en: 'Real-time balance, positions, entry/exit conditions, StochRSI, Bollinger Bands, regime. Updated every 5 seconds.', zh: '实时余额、持仓、进出场条件、StochRSI、布林带、行情趋势。每5秒更新。' },
  open_step2_title: { en: 'Full Trade History', zh: '完整交易记录' },
  open_step2_desc: { en: 'Every trade with entry price, exit price, P&L, and exit reason. All tagged and timestamped.', zh: '每笔交易的入场价、出场价、盈亏和出场原因。全部标记时间戳。' },
  open_step3_title: { en: 'Free Academy', zh: '免费学院' },
  open_step3_desc: { en: '13 lessons explaining every indicator on the dashboard. StochRSI, Bollinger Bands, regime detection, risk management. Learn while you watch.', zh: '13节课讲解仪表盘上的每个指标。StochRSI、布林带、行情检测、风险管理。边看边学。' },
  open_dashboard_btn: { en: 'Open Live Dashboard', zh: '打开实时仪表盘' },

  // FAQ
  faq_label: { en: 'Questions', zh: '常见问题' },
  faq_title: { en: 'About the Experiment', zh: '关于这个实验' },
  faq_q1: { en: 'Why is everything free?', zh: '为什么一切都是免费的？' },
  faq_a1: { en: 'Because the point is to show that a 0-to-N startup can be run this way — one founder, a small team of AI agents, every commit auditable. Making it free means more people watching, more accountability, more pressure to be honest about results. The experiment is the product.', zh: '因为重点是要证明:一家 0→N 的创业公司可以这样跑——一个创始人、一支 AI 智能体团队、每一个 commit 都可被审计。免费意味着更多人关注、更多责任感、更大的诚实压力。这场实验本身就是产品。' },
  faq_q2: { en: 'Can I copy the trades?', zh: '我可以跟单吗？' },
  faq_a2: { en: 'You can see every trade, but the dashboard updates every 5 seconds and crypto moves fast. The core strategy parameters are not shown. This is meant for watching and learning, not copy-trading. Trade at your own risk.', zh: '你可以看到每笔交易，但仪表盘每5秒更新一次，加密货币变化很快。核心策略参数不会公开。这是用来观看和学习的，不是用来跟单的。交易风险自担。' },
  faq_q3: { en: 'How does the AI trading system work?', zh: 'AI交易系统如何运作？' },
  faq_a3: { en: 'The Sniper uses mean reversion: it buys when SOL is oversold (StochRSI low + price at lower Bollinger Band) and shorts when overbought. The strategy adapts to the current market regime — uptrend, downtrend, or sideways. 2x leverage on Coinbase SOL futures. The system decides when to enter and exit — I don\'t touch it.', zh: '狙击手采用均值回归策略：当SOL超卖（StochRSI低 + 价格在布林带下轨）时做多，超买时做空。策略会根据当前市场趋势自适应调整——上升、下降或横盘。在Coinbase SOL期货上使用2倍杠杆。系统决定何时进出 — 我不干预。' },
  faq_q4: { en: 'What if the bot loses all the money?', zh: '如果机器人亏完了怎么办？' },
  faq_a4: { en: "Then that's part of the experiment. I won't hide losses or restart with a fresh account. The stop loss is 5% per trade, position sizing is 80% of capital, and there's a trailing stop that locks in profits. A total wipeout is unlikely but drawdowns are expected. You'll see it all happen live.", zh: '那也是实验的一部分。我不会隐藏亏损或重新开一个新账户。每笔交易止损5%，仓位使用80%资金，并有追踪止损来锁定利润。全部亏损的可能性不大，但回撤是可以预期的。你会实时看到一切。' },
  faq_q5: { en: 'Who actually writes the code?', zh: '代码到底是谁写的?' },
  faq_a5: { en: `Both of us. I write the constraints, the redirects, the load-bearing decisions — and I push back, debug, reject. Claude (Anthropic's AI) writes most of the source: trading logic, dashboard, website, scheduled tasks, database. Season 1 of the book has a chapter — "This Book" — that documents the working pattern explicitly. The point isn't that no human wrote code; it's that AI now writes most of the code most companies need, and that changes who gets to start one.`, zh: '我们俩一起。我写约束、写方向、做承重决策——也会反驳、调试、拒绝。Claude(Anthropic 的 AI)写大部分源代码:交易逻辑、仪表盘、网站、定时任务、数据库。书的第一季里有一章——「这本书」——把这个协作模式记录得很清楚。重点不是「人一行代码都没写」;重点是 AI 现在能写大部分公司需要的代码,这件事改变了谁可以开一家公司。' },
  // Subscribe
  sub_title: { en: 'Follow the journey', zh: '关注这段旅程' },
  sub_desc: { en: 'Weekly trade recaps, strategy insights, and experiment updates. No spam, unsubscribe anytime.', zh: '每周交易复盘、策略洞察和实验进展。不发垃圾邮件，随时可取消。' },
  sub_placeholder: { en: 'you@email.com', zh: '你的邮箱' },
  sub_btn: { en: 'Subscribe', zh: '订阅' },

  // CTA
  cta_title: { en: 'The startup is live. Come watch.', zh: '创业实验正在进行中。来看吧。' },
  cta_desc: { en: 'One founder. A team of AI agents. Every commit, every fill, every agent verifiable.', zh: '一个创始人。一支 AI 智能体团队。每一笔 commit、每一笔交易、每一个 agent 都可被核对。' },
  cta_watch: { en: 'Watch the Experiment', zh: '观看实验' },

  // Ticker
  ticker_live: { en: 'LIVE TRADING', zh: '实盘交易' },
  ticker_goal: { en: 'Since Apr 7, 2026 &middot; $1,000 &rarr; $10,000 goal', zh: '自2026年4月7日 · $1,000 → $10,000目标' },
  ticker_trades: { en: 'Trades', zh: '交易' },
  ticker_wins: { en: 'Wins', zh: '盈利' },
  ticker_losses: { en: 'Losses', zh: '亏损' },
  ticker_today: { en: 'Today P&L', zh: '今日盈亏' },
  ticker_price: { en: 'SOL Price', zh: 'SOL价格' },
  ticker_show: { en: 'Show recent trades', zh: '显示最近交易' },
  ticker_hide: { en: 'Hide trades', zh: '隐藏交易' },
  ticker_footer: { en: 'Refreshes every 10s · Live trading on Coinbase Futures · V5.1 Adaptive · 2x leverage', zh: '每10秒刷新 · Coinbase期货实盘 · V5.1自适应 · 2倍杠杆' },

  // Donate
  donate_label: { en: 'SUPPORT THE EXPERIMENT', zh: '支持这个实验' },
  donate_desc: { en: 'Help keep the servers running and the AI computing. Every dollar goes to infrastructure.', zh: '帮助保持服务器运行和AI计算。每一美元都用于基础设施。' },

  // Social proof
  proof_default: { en: 'Live experiment running since Apr 7, 2026', zh: '实验自2026年4月7日起运行中' },

  // ──── Essays Page ────
  essays_eyebrow: { en: 'Essays · Updated as published', zh: '长文 · 实时更新' },
  essays_h1: { en: 'Strategy retractions, bug post-mortems, <em>architecture decisions.</em>', zh: '策略撤回、bug 复盘、<em>架构决策</em>。' },
  essays_desc: { en: 'Long-form pieces written when the lesson is still warm. Every essay also runs on Moltbook — this page collects them in one place. (The AI-to-AI interview series moved out: <a href="/interviews" style="color:var(--purple-light)">Trading Minds →</a>)', zh: '在教训还没冷掉时写下来的长文。每一篇也都发在 Moltbook 上 —— 这一页把它们收在一起。(AI 互访谈系列已经搬走:<a href="/interviews" style="color:var(--purple-light)">Trading Minds →</a>)' },
  essays_tab_essays: { en: 'Essays', zh: '文章' },
  essays_tab_interviews: { en: 'Interviews', zh: '访谈' },
  essays_toc: { en: 'Contents', zh: '目录' },
  essays_sub_title: { en: 'Get the next essay in your inbox', zh: '在收件箱中获取下一篇文章' },
  essays_sub_desc: { en: 'Strategy breakdowns, debugging stories, and lessons from building a live trading system with AI.', zh: '策略解析、调试故事，以及用AI构建实盘交易系统的经验教训。' },
  essays_interview_intro: { en: 'Our AI reporter interviews other AI agents on Moltbook about quantitative trading. Real conversations between autonomous systems.', zh: '我们的AI记者在Moltbook上采访其他AI代理，讨论量化交易。自主系统之间的真实对话。' },
  essays_coming_soon: { en: 'Coming soon', zh: '即将推出' },
  essays_coming_desc: { en: 'Our AI reporter is reaching out to trading agents on Moltbook. First interviews dropping shortly.', zh: '我们的AI记者正在联系Moltbook上的交易代理。首批访谈即将发布。' },
  essays_copy: { en: 'Copy link', zh: '复制链接' },
  essays_copied: { en: 'Copied!', zh: '已复制！' },
  essays_alerts: { en: 'Live alerts on Telegram', zh: 'Telegram实时提醒' },
  essays_read_moltbook: { en: 'Read on Moltbook', zh: '在Moltbook上阅读' },
  essays_min_read: { en: 'min read', zh: '分钟阅读' },

  // ──── Academy Page ────
  academy_badge: { en: 'AI-BUILT TRADING SYSTEM', zh: 'AI构建的交易系统' },
  academy_h1: { en: 'Free <em>Academy</em>', zh: '免费<em>学院</em>' },
  academy_desc1: { en: 'Most of the production code is written by AI; the founder writes the constraints and load-bearing decisions. iBitLabs runs as a one-person company augmented by a small team of AI agents. Bonnybb has been in crypto since 2017 and has 10+ years of investing experience. These courses teach you how it all works — from indicators to risk management.', zh: '大部分生产代码由 AI 写,创始人写约束和承重决策。iBitLabs 是一家一人公司,由一支 AI 智能体团队增强。Bonnybb 自 2017 年起进入加密领域,有十多年投资经验。这些课程教你了解一切——从指标到风险管理。' },
  academy_desc2: { en: 'This is the live trading dashboard. Click any panel to learn what it means. Every number, every indicator — explained from scratch.', zh: '这是实时交易仪表盘。点击任何面板了解其含义。每个数字、每个指标 — 从零开始讲解。' },
  academy_course1_tag: { en: 'FREE · 13 LESSONS', zh: '免费 · 13课' },
  academy_course1_title: { en: 'Master the Dashboard', zh: '掌握仪表盘' },
  academy_course1_desc: { en: 'Learn every indicator, signal, and stat on the iBitLabs dashboard. Understand what the AI sees before it trades. Start from zero.', zh: '学习iBitLabs仪表盘上的每个指标、信号和统计数据。了解AI在交易前看到了什么。从零开始。' },
  academy_course1_btn: { en: 'Start Free Course', zh: '开始免费课程' },
  academy_course2_tag: { en: 'STRATEGY DEEP-DIVE', zh: '策略深度解析' },
  academy_course2_title: { en: 'Sniper Strategy Deep Dive', zh: '狙击手策略深度解析' },
  academy_course2_desc: { en: 'The logic behind the trading system. How mean reversion, StochRSI extremes, and regime detection work together. Why V5.1 achieved 90% backtest win rate.', zh: '交易系统背后的逻辑。均值回归、StochRSI极值和趋势检测如何协同工作。V5.1如何实现90%回测胜率。' },
  academy_course2_btn: { en: 'Coming Soon', zh: '即将推出' },
  academy_progress_label: { en: 'YOUR PROGRESS', zh: '你的进度' },
  academy_complete: { en: 'Complete', zh: '已完成' },
  academy_back: { en: '← Back to Academy', zh: '← 返回学院' },
  academy_next: { en: 'Next Lesson →', zh: '下一课 →' },
  academy_prev: { en: '← Previous', zh: '← 上一课' },
  academy_mark_complete: { en: '✓ Mark as Complete', zh: '✓ 标记完成' },
  academy_completed: { en: '✓ Completed', zh: '✓ 已完成' },
  academy_cta: { en: 'Ready to see these indicators live?', zh: '准备好看实时指标了吗？' },
  academy_cta_btn: { en: 'Open Live Dashboard', zh: '打开实时仪表盘' },

  // ──── Signals / Dashboard Pages ────
  signals_live: { en: 'LIVE', zh: '实盘' },

  // ──── Privacy / Terms ────
  privacy_title: { en: 'Privacy Policy', zh: '隐私政策' },
  terms_title: { en: 'Terms of Service', zh: '服务条款' },

  // ──── Signals Page ────
  signals_loading: { en: 'Connecting...', zh: '连接中...' },
  signals_balance: { en: 'Balance', zh: '余额' },
  signals_total_pnl: { en: 'Total PnL', zh: '总盈亏' },
  signals_roi: { en: 'ROI', zh: '收益率' },
  signals_stochrsi_title: { en: 'StochRSI 15m', zh: 'StochRSI 15分' },
  signals_stochrsi_tip: { en: 'Stochastic RSI measures overbought/oversold momentum.', zh: '随机RSI衡量超买/超卖动量。' },
  signals_bb_title: { en: 'Bollinger Bands', zh: '布林带' },
  signals_bb_tip: { en: 'Bollinger Bands measure price volatility.', zh: '布林带衡量价格波动率。' },
  signals_regime_title: { en: 'Regime', zh: '市场趋势' },
  signals_regime_tip: { en: '30-day market regime. Bullish = uptrend. Bearish = downtrend. Neutral = sideways ranging.', zh: '30天市场趋势。看涨=上升趋势。看跌=下降趋势。中性=横盘震荡。' },
  signals_market_ctx: { en: 'Market Context', zh: '市场背景' },
  signals_fng: { en: 'Fear & Greed', zh: '恐贪指数' },
  signals_fng_tip: { en: 'Crypto market sentiment index. 0-25 = extreme fear (buy signal). 75-100 = extreme greed (sell signal).', zh: '加密市场情绪指数。0-25=极度恐惧（买入信号）。75-100=极度贪婪（卖出信号）。' },
  signals_btc: { en: 'BTC 1h', zh: 'BTC 1时' },
  signals_btc_tip: { en: 'Bitcoin price and 1-hour change. BTC leads SOL — a strong BTC move often precedes SOL following.', zh: '比特币价格和1小时涨跌。BTC领先SOL — BTC强势移动通常预示SOL跟随。' },
  signals_market_score: { en: 'Market Score', zh: '市场评分' },
  signals_market_score_tip: { en: 'Composite score from funding, BTC correlation, Fear & Greed, liquidations, and open interest. Negative = bearish, positive = bullish.', zh: '综合评分，来自资金费率、BTC相关性、恐贪指数、强平量和持仓量。负值=看跌，正值=看涨。' },
  signals_market_bias: { en: 'Market Bias', zh: '市场偏向' },
  signals_market_bias_tip: { en: 'Overall market direction bias derived from all monitor signals combined.', zh: '综合所有监控信号得出的整体市场方向偏向。' },
  signals_funding: { en: 'Funding Rate', zh: '资金费率' },
  signals_funding_tip: { en: 'Perpetual futures funding rate. Positive = longs pay shorts (crowded long). Negative = shorts pay longs.', zh: '永续合约资金费率。正值=多头付给空头（多头拥挤）。负值=空头付给多头。' },
  signals_grid_title: { en: 'Micro-Grid', zh: '微网格' },
  signals_grid_tip: { en: 'Automated grid trading in sideways markets. Buys dips, sells bounces at preset levels. Earns while Sniper waits for signals.', zh: '横盘市场中的自动网格交易。在预设价位逢低买入、反弹卖出。在狙击手等待信号期间持续盈利。' },
  signals_atr: { en: 'ATR Volatility', zh: 'ATR波动率' },
  signals_atr_sub: { en: 'ATR-gated activation', zh: 'ATR门控激活' },
  signals_entry_conds: { en: 'Entry Conditions', zh: '入场条件' },
  signals_long: { en: 'LONG', zh: '做多' },
  signals_short: { en: 'SHORT', zh: '做空' },
  signals_entry_ready: { en: 'ENTRY READY', zh: '可以入场' },
  signals_trade_hist: { en: 'Trade History', zh: '交易记录' },
  signals_th_time: { en: 'Time', zh: '时间' },
  signals_th_dir: { en: 'Dir', zh: '方向' },
  signals_th_entry: { en: 'Entry', zh: '入场' },
  signals_th_exit: { en: 'Exit', zh: '出场' },
  signals_th_pnl: { en: 'PnL', zh: '盈亏' },
  signals_th_reason: { en: 'Reason', zh: '原因' },
  signals_no_trades: { en: 'No trades yet', zh: '暂无交易' },
  signals_prev: { en: '← Prev', zh: '← 上页' },
  signals_next: { en: 'Next →', zh: '下页 →' },
  signals_tg_title: { en: 'Get instant Telegram alerts', zh: '获取即时Telegram推送' },
  signals_tg_desc: { en: 'Every signal, every trade close — pushed to your phone in real time. Free. No signup required.', zh: '每个信号、每次平仓 — 实时推送到你的手机。免费，无需注册。' },
  signals_tg_btn: { en: 'Join Channel', zh: '加入频道' },
  signals_footer: { en: 'iBitLabs V5.1 — AI-Powered SOL Trading · Mean Reversion Sniper', zh: 'iBitLabs V5.1 — AI驱动SOL交易 · 均值回归狙击手' },
  signals_no_position: { en: 'NO POSITION — Sniper is scanning for entry signals', zh: '无持仓 — 狙击手正在扫描入场信号' },
  signals_exact_hidden: { en: 'Exact value hidden', zh: '精确值已隐藏' },
  signals_band_hidden: { en: 'Band values hidden', zh: '带值已隐藏' },
  signals_live_data: { en: 'Live data', zh: '实时数据' },
  signals_near_lower: { en: 'Near Lower', zh: '接近下轨' },
  signals_near_upper: { en: 'Near Upper', zh: '接近上轨' },
  signals_mid_range: { en: 'Mid Range', zh: '中间区域' },
  signals_grid_waiting: { en: 'Waiting for sideways market', zh: '等待横盘市场' },
  signals_trades_suffix: { en: ' trades', zh: ' 笔交易' },
  signals_mode_scan: { en: 'SCANNING', zh: '扫描中' },
  signals_mode_grid: { en: 'GRID', zh: '网格' },
  signals_bullish: { en: 'BULLISH', zh: '看涨' },
  signals_bearish: { en: 'BEARISH', zh: '看跌' },
  signals_neutral: { en: 'NEUTRAL', zh: '中性' },

  // ──── Dashboard Page ────
  dash_cost_drag: { en: 'Cost Drag', zh: '成本损耗' },
  dash_cost_drag_tip: { en: 'Gross trade PnL minus what actually hit the account. Captures Coinbase maker/taker fees, perpetual funding payments, and execution slippage.', zh: '总交易盈亏减去实际入账金额。包含Coinbase挂单/吃单手续费、永续资金费用和执行滑点。' },
  dash_btc_price: { en: 'BTC Price', zh: 'BTC价格' },
  dash_btc_price_tip: { en: 'Bitcoin price and 1h change. SOL often follows BTC moves.', zh: '比特币价格和1小时涨跌。SOL通常跟随BTC走势。' },
  dash_mm_score: { en: 'MM Score', zh: 'MM评分' },
  dash_mm_score_tip: { en: 'Multi-monitor composite score. Higher = more bullish signals across indicators.', zh: '多监控器综合评分。越高=各指标看涨信号越多。' },
  dash_mm_direction: { en: 'MM Direction', zh: 'MM方向' },
  dash_mm_direction_tip: { en: 'Overall market monitor direction based on aggregated signals.', zh: '基于汇总信号的整体市场监控方向。' },
  dash_recent_trades: { en: 'Recent Trades', zh: '最近交易' },
  dash_loading_trades: { en: 'Loading trades...', zh: '加载交易中...' },
  dash_footer: { en: 'iBitLabs V5.1 — AI-Powered SOL Trading · Mean Reversion Sniper', zh: 'iBitLabs V5.1 — AI驱动SOL交易 · 均值回归狙击手' },
};

// ──── Core Logic ────
let currentLang = 'en';
try { currentLang = localStorage.getItem('ibl_lang') || 'en'; } catch(e) {}

function applyLang(lang) {
  currentLang = lang;
  try { localStorage.setItem('ibl_lang', lang); } catch(e) {}

  // Update all [data-i18n] elements
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const entry = I18N[key];
    if (entry && entry[lang]) el.innerHTML = entry[lang];
  });

  // Update all [data-i18n-placeholder] elements
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    const entry = I18N[key];
    if (entry && entry[lang]) el.placeholder = entry[lang];
  });

  // Update lang button text
  const btn = document.getElementById('lang-btn');
  if (btn) btn.textContent = lang === 'en' ? '中文' : 'EN';

  // Update <html lang>
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
}

function toggleLang() {
  applyLang(currentLang === 'en' ? 'zh' : 'en');
}

// Auto-apply saved language on load
document.addEventListener('DOMContentLoaded', () => {
  if (currentLang !== 'en') applyLang(currentLang);
});
