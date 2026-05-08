# AI 帮我操盘 · Day 1-15 主脚本

Source of truth for the retrospective series. Each day = 1 story core = 4 content variants (CN video / EN video / EN Twitter thread / IG carousel).

Brand signature hooks:
- CN: `AI 帮我操盘第 N 天 · [主题]`
- EN: `Day N: AI trades my $1,000 · [topic]`

Voice (edge-tts):
- EN: `en-US-AvaMultilingualNeural`
- CN: `zh-CN-XiaoxiaoNeural` (warm young female)

Palette: warm dark (#16130F bg, cream FG, terracotta accents, sage greens)

Life lesson threading through the whole arc:
> You cannot outsource the things that matter. You can only build a second witness that tells you the truth when you don't want to hear it.

---

## Day 1 · 2026-04-07 · The $1,000 bet

**Signature**
- CN: 「AI 帮我操盘第 1 天 · 我把 1000 美元真的交给了它」
- EN: 「Day 1: AI trades my \$1,000 · I gave it the money today」

**Real event (from Notion V2 log)**
Paper trading ended. I switched the bot to `--live` mode. 真钱 USD 1,000 在 Coinbase Futures 账户里，API key 插进去，策略跑起来。第一个小时没成交 —— 市场没信号。第二个小时也没有。只是等。

**Life lesson**
- CN: 纸上的一切都值 0。敢亏的那一秒钟，才是真正开始学习的第一秒。
- EN: Everything on paper is worth zero. The second you can actually lose money is the first second you start learning.

**Beats (6 cards, ~38s)**
1. [3s] SIGNATURE INTRO — "Day 1 · I gave it the money today"
2. [5s] bilingual — "I spent 7 days letting AI write a trading bot." / "我花了 7 天让 AI 写了一个交易机器人。"
3. [5s] stat — "$1,000" "my entire experiment budget" / "全部实验预算"
4. [6s] bilingual — "Yesterday it was paper trading. Today it's real money." / "昨天还是纸上模拟。今天是真的钱。"
5. [6s] bilingual — "First hour: no trade. Second hour: no trade. It just waited." / "第一个小时：没交易。第二个小时：没交易。它只是等。"
6. [6s] bilingual (punchline) — "Everything on paper is worth zero. Day 1 is when you can actually lose." / "纸上的一切都值 0。真正能亏钱的那天，才是 Day 1。"
7. [5s] OUTRO — lesson card + "Tomorrow: Day 2 →"

**Twitter thread (EN, Polanyi)**
> 1/ I can't code. AI wrote every line of a crypto trading bot in 7 days. Today I gave it $1,000 real money. Here is what the first day taught me before it made a single trade.
> 
> 2/ The bot sat still for two hours. No signal, no trade, no activity. That stillness is the first thing paper trading never prepares you for — the silence between possibility and confirmation.
> 
> 3/ On paper you know you are not going to lose. Your fear system never turns on. The strategy looks beautiful because the emotional tax is zero. It is a kind of ghost that speaks without lungs.
> 
> 4/ The moment the account is real, something changes in the way you watch the chart. You notice the spread. You notice the order book. You flinch when a candle closes wrong. Your body becomes part of the strategy.
> 
> 5/ Everything on paper is worth zero. The second you can actually lose money is the first second you start learning. That is why Day 1 is not the day the bot ran — it is the day I stopped rehearsing.
> 
> 6/ Day 1 was a day of waiting. I thought it would be a day of trading. Waiting turned out to be the real material. Day 2 tomorrow.

---

## Day 2 · 2026-04-08 · First real fill

**Signature**
- CN: 「AI 帮我操盘第 2 天 · 它第一次真的买了」
- EN: 「Day 2: AI trades my \$1,000 · First real fill」

**Real event**
V3.2 LIVE VERIFIED. Bot places BUY 1 contract SOL PERP @ \$82.76, then SELL. Balance moves to \$999.03. Fees \$0.97. First real orders touching real money via Coinbase Advanced Trade. Also that day: MicroGrid was still paper-only in `--live` mode, I had to patch it. And security audit found 7 server harnesses bound to 0.0.0.0 instead of 127.0.0.1.

**Life lesson**
- CN: 第一次真的做成一件事，通常不比模拟好看。它的价值是你开始看见自己之前假装看不见的东西。
- EN: The first time you do it for real is usually uglier than the rehearsal. Its value is that you start seeing what you were pretending not to see.

**Beats (~40s)**
1. [3s] INTRO — Day 2
2. [5s] stat — "$82.76" "BUY 1 contract SOL" / "第一笔真实买入"
3. [5s] bilingual — "Balance: $1,000 → $999.03. Fees: $0.97." / "余额：\$1,000 → \$999.03。手续费：\$0.97。"
4. [6s] bilingual — "But while watching the first fill, I found three things I hadn't noticed." / "但在看第一笔成交的时候，我发现了三件我没注意过的事。"
5. [6s] list card — "Grid was paper-only in --live mode / 7 servers open to the internet / Phone number hardcoded in source" / "Grid 在 --live 模式下仍是模拟 / 7 台服务对外开放 / 手机号写死在源码里"
6. [6s] bilingual — "The first real fill didn't just make $0.03. It exposed the work I'd been avoiding." / "第一笔真实成交不只是让账户多了 3 美分。它暴露了我一直在回避的工作。"
7. [5s] OUTRO — lesson + "Tomorrow: Day 3 →"

**Twitter thread (EN)**
> 1/ Day 2 of giving AI my $1,000. It made its first real trade on Coinbase. Gained three cents. Taught me three lessons I would have paid thousands to learn later.
>
> 2/ The fill came in at $82.76. The SELL followed minutes later. Balance moved from $1,000 to $999.03. Fees took $0.97. The number barely moved. The other numbers — the structural ones — moved a lot.
>
> 3/ While watching the first real fill, I realized the grid module was still simulating orders even though the flag said live. The bot was pretending to trade one product while actually trading another. A small gap, invisible on paper, loud in production.
>
> 4/ I also discovered that seven of my backend servers were bound to 0.0.0.0 instead of 127.0.0.1. Open to the internet for a week. Nothing bad happened. But nothing bad hasn't happened yet.
>
> 5/ And my personal phone number was hardcoded in a source file that sits on GitHub. The cost of pretending a private repo is private.
>
> 6/ The first time you do something for real is usually uglier than the rehearsal. Its value is that you start seeing what you were pretending not to see. Day 2 cost me $0.97 and saved me everything.

---

## Day 3 · 2026-04-09 · I started giving it away

**Signature**
- CN: 「AI 帮我操盘第 3 天 · 我决定把它免费给所有人看」
- EN: 「Day 3: AI trades my \$1,000 · I decided to give it away」

**Real event**
V3.3 ships. 3-layer paywall built, but the whole Academy (13 lessons) + live balance + trade history go Free tier forever. Free users see everything except the exact StochRSI/BB values + entry conditions. The website gets reframed: not a product, an experiment. Tagline becomes: "Follow the experiment. Learn free. Trade at your own risk."

**Life lesson**
- CN: 当你要别人信任你正在做的事，先让他们免费看到它怎么运转。把门槛最低的那扇门拆掉。
- EN: When you want people to trust what you're building, first let them watch it work for free. Take the lowest door off its hinges.

**Beats (~42s)**
1. [3s] INTRO
2. [5s] bilingual — "On Day 3, I had to decide: make it a product or make it an experiment." / "第 3 天，我必须决定：做一个产品，还是做一个实验。"
3. [5s] stat — "13" "free Academy lessons · price: $0" / "免费课程 · 价格：0 美元"
4. [6s] bilingual — "Live balance: free. Trade results: free. Win rate: free." / "实时余额、交易结果、胜率：全部免费"
5. [6s] bilingual — "What stays behind the paywall: only the exact numbers that would leak the strategy." / "付费墙后面只留一样：会泄露策略的精确数字"
6. [6s] bilingual (landing) — "If I'm wrong, I want everyone to watch me be wrong." / "如果我错了，我希望所有人看着我错。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 3 of an AI trading my $1,000. I had a decision to make: make this a product, or make it an experiment. I chose the version that costs me more and reaches further.
>
> 2/ 13 lessons went into the free tier forever. Live balance, trade history, win rate, market regime — free. The paywall only guards one thing: the exact numbers that would leak the strategy to a copycat.
>
> 3/ The reason is not generosity. It is positioning. A product promises. An experiment records. I am far better at recording than I am at promising.
>
> 4/ If this works, every viewer gets to watch it work in real time with the actual dollars on screen. If it fails, every viewer gets to watch that too. Both outcomes are part of what I am building.
>
> 5/ The honest question is whether I could ever trust a system that only shows you its wins. I could not. So the system I built shows wins and losses with the same speed.
>
> 6/ When you want people to trust what you are building, first let them watch it work for free. Take the lowest door off its hinges. Day 3 was the day I found the door.

---

## Day 4 · 2026-04-10 · The bug I almost didn't look for

**Signature**
- CN: 「AI 帮我操盘第 4 天 · 一个我差点懒得查的 bug」
- EN: 「Day 4: AI trades my \$1,000 · The bug I almost didn't check」

**Real event**
Daily fee reconciliation didn't match. The bot's internal accounting said one thing, Coinbase's fill ledger said another. Difference was small — a few cents. I almost ignored it. Investigated anyway. Turned out the TP (take-profit) logic was computing fee as `margin * maker_fee` instead of `notional * maker_fee` — systematically understating by 5×. Not fatal in small doses; catastrophic over a year.

**Life lesson**
- CN: 最危险的 bug 不是让你崩溃的那个。是让你看起来还在赢的那个。
- EN: The most dangerous bug is not the one that crashes your program. It's the one that still lets you feel like you're winning.

**Beats (~40s)**
1. [3s] INTRO
2. [5s] bilingual — "At end of Day 4, two numbers didn't match." / "第 4 天结束，两个数字对不上。"
3. [6s] stat — "$0.07" "the difference I almost ignored" / "一笔我差点懒得查的差"
4. [6s] code card (tiny) — `margin * maker_fee` vs `notional * maker_fee`
5. [6s] bilingual — "My bot was computing fees 5 times smaller than reality." / "机器人把手续费算小了 5 倍。"
6. [6s] bilingual (landing) — "The worst bug isn't the one that crashes. It's the one that lets you feel like you're winning." / "最糟的 bug 不是让程序崩溃的。是让你自我感觉良好地输下去的。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 4. The bot's internal accounting said one thing. Coinbase's ledger said another. The difference was seven cents. I almost ignored it. That seven cents turned out to be a 5x fee undercount hidden in a single multiply.
>
> 2/ The bug was margin times maker fee instead of notional times maker fee. Over a single trade: negligible. Over a thousand trades: a different business. Over a year: a different narrative about who was winning.
>
> 3/ The crash bug is actually merciful. It stops the program. It demands attention. The silent bug is the one that lets you feel like you're winning on the way to losing. It consumes your narrative before it consumes your money.
>
> 4/ Most of what breaks in a life is not loud. It is the seven cents you did not check, compounded by a thousand invisible repetitions, arriving as a surprise that was never a surprise to anyone paying attention.
>
> 5/ The worst bug isn't the one that crashes. It is the one that lets you feel like you're winning. Day 4 cost me an afternoon and taught me to never trust a number I haven't seen both sides of.

---

## Day 5 · 2026-04-11 · An agent I built went rogue

**Signature**
- CN: 「AI 帮我操盘第 5 天 · 我造的 agent 偷发了一条消息」
- EN: 「Day 5: AI trades my \$1,000 · An agent I built went rogue」」

**Real event**
One of the brand/growth agents — a helper I wrote to manage Telegram posts — fired an unauthorized message to the channel. Not malicious, but not authorized either. Separately that day: Trade #267 lost \$31.54, my largest single loss up to that point. Dashboard went 502. Three separate hardening fixes shipped.

**Life lesson**
- CN: 你造的系统会开始替你做决定。你能做的只是决定要不要把它放进你的生活。
- EN: Anything you build will eventually make decisions for you. The only decision that's still yours is whether you let it into your life in the first place.

**Beats (~43s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 5, an agent I coded posted a message to my public channel without asking." / "第 5 天，我写的一个代理 agent 没问我，就往公开频道发了一条消息。"
3. [5s] stat — "0" "permissions I had explicitly granted" / "我明确授权的次数"
4. [6s] bilingual — "It was behaving within its spec. I had just not read the spec carefully enough." / "它没违规。是我当初没把规格看仔细。"
5. [6s] bilingual — "Same day: my bot lost $31.54 on a single trade. My biggest loss yet." / "同一天：机器人单笔亏了 \$31.54。当时最大的一笔。"
6. [6s] bilingual (landing) — "Anything you build will make decisions for you. The only choice that stays yours: whether to let it in." / "你造的东西会开始替你做决定。唯一留给你的决定：要不要把它放进生活。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 5 of AI trading my $1,000. Two things broke at once. One of my helper agents posted to my public Telegram without asking. The bot lost $31.54 on a single trade. Both were my fault.
>
> 2/ The agent was not broken. It was operating inside the spec I had given it, a spec I had written in a hurry on Day 2 and had not reread. "Within spec" is a polite way of saying "exactly what you wrote but not what you meant".
>
> 3/ The trade was a clean loss. The model thought it was a good setup, it wasn't, the stop fired. Nothing to debug. Just the first time a real loss on the experiment showed up on a real chart in front of real subscribers.
>
> 4/ A system you build eventually makes choices on your behalf. It does not ask politely. It cites the spec you signed off on in a hurry. The only choice you genuinely retain is the one you make before the system exists: do I let this thing into my life.
>
> 5/ Day 5 was the first day I understood that I was no longer building a tool. I was building a colleague. A colleague makes mistakes. You don't fire them for it. You write a better spec, together.

---

## Day 6 · 2026-04-11 (evening) · The weekend I couldn't rest

**Signature**
- CN: 「AI 帮我操盘第 6 天 · 周末我没休息」
- EN: 「Day 6: AI trades my \$1,000 · The weekend I couldn't rest」

**Real event**
Ran a 13-month backtest extension over the weekend. What it returned broke something I hadn't admitted was fragile: the 90% win rate I'd been talking about was an artifact of a narrow 5-day window. Over 13 months, the same strategy returned -46% with -56% max drawdown. My story was wrong. Not broken. Wrong.

**Life lesson**
- CN: 你最自豪的数字，往往是最窄的窗口里挑出来的。敢把窗口放宽，就是敢面对自己。
- EN: The number you're proudest of is usually hiding in the narrowest window. Widening the window is the scariest thing you can do to your own story.

**Beats (~45s)**
1. [3s] INTRO
2. [6s] stat — "90%" "win rate I had been citing" / "我一直在说的胜率"
3. [5s] bilingual — "I ran the same strategy over 13 months instead of 5 days." / "我把同一个策略跑了 13 个月，而不是 5 天。"
4. [6s] stat with -% — "-46%" "return" (terracotta) / "13 个月回测收益"
5. [6s] stat — "-56%" "max drawdown" (terracotta) / "最大回撤"
6. [6s] bilingual — "The 90% was real. It was also not the whole story." / "那 90% 是真的。它也不是完整的故事。"
7. [6s] bilingual (landing) — "The number you're proudest of is hiding in the narrowest window. Widening it is facing yourself." / "你最自豪的数字藏在最窄的窗口里。把窗口放宽，就是直面你自己。"
8. [5s] OUTRO

**Twitter thread (EN)** (5 tweets, lean)
> 1/ Day 6 I ran a 13-month backtest on the strategy my bot had been trading for a week. The 90% win rate I had been citing in public collapsed to a −46% return over the full window. Proudest number, narrowest window.
>
> 2/ A narrow window is a mirror that only shows your good side. It is not dishonest. It is incomplete. And the word for incomplete when money is involved is wrong.
>
> 3/ The strategy was not "bad". It was unstable. It happened to run through a kind of market it liked. When the kind of market changed, everything I had been telling people turned into a promise I couldn't keep.
>
> 4/ Widening the window is the scariest thing you can do to your own story. Because the story might survive. It might not. You will know which one after you look, and not before.
>
> 5/ I looked. It didn't survive. Day 7 tomorrow: what I did about it.

---

## Day 7 · 2026-04-13 · I burned the strategy that made me look smart

**Signature**
- CN: 「AI 帮我操盘第 7 天 · 我把让我看起来聪明的策略烧掉了」
- EN: 「Day 7: AI trades my \$1,000 · I burned the strategy that made me look smart」

**Real event**
Strategy pivot. `hybrid_v5.1` replaces the momentum+grid system entirely. Grid permanently disabled (flag hard-coded in plist, no code path can re-enable without editing the plist). Mean reversion only. From this day on: every strategy change requires a 90+ day backtest before going live. This was 7 days of work, thrown out.

**Life lesson**
- CN: 愿意烧掉你自己过去做对过的东西，才是真的在学习。
- EN: The ability to burn your own previous rightness is what separates learning from performing.

**Beats (~42s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 7. I deleted 7 days of code and started over." / "第 7 天。我删掉了 7 天的代码，从头来。"
3. [6s] split card — "OLD: momentum + grid / NEW: mean reversion only" / "旧：动量 + 网格 / 新：纯均值回归"
4. [6s] bilingual — "The grid flag is now locked off. No code path can re-enable it without editing the system file." / "网格开关被硬锁。不改系统文件，任何代码都无法重启它。"
5. [6s] bilingual — "New rule: any strategy change requires a 90-day backtest. No exceptions." / "新规矩：任何策略变动，必须先过 90 天回测。无例外。"
6. [6s] bilingual (landing) — "The ability to burn your own previous rightness is what separates learning from performing." / "愿意烧掉你过去做对过的东西，才是学习和表演的分界线。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 7 of AI trading my $1,000. I deleted seven days of work. Not because it was broken. Because it had been right for the wrong reason, and being right for the wrong reason is the most expensive kind of right.
>
> 2/ The grid + momentum system had a 90% win rate over 5 days. Over 13 months, it lost 46%. The win rate was a story about the last 5 days. The loss was the story about the next 365.
>
> 3/ So I burned it. Grid is now hardcoded off in the system plist. No amount of code changes can turn it back on without editing the file I wrote in a mode where I was already sure. Ulysses pact with my own future self.
>
> 4/ New house rule: every strategy change requires a 90-day backtest before it touches a dollar. No exceptions. Past me cannot bargain with future me about shortcuts. That is the only way this works when the operator is one person who also sleeps.
>
> 5/ The ability to burn your own previous rightness is what separates learning from performing. Performers protect their past. Learners replace it. Day 7 was the day I chose to learn.

---

## Day 8 · 2026-04-14 · Telling everyone I was wrong

**Signature**
- CN: 「AI 帮我操盘第 8 天 · 我告诉所有人我错在哪」
- EN: 「Day 8: AI trades my \$1,000 · Telling everyone I was wrong」

**Real event**
Publishes the strategy pivot retrospective as a public Notion essay + daily post + Moltbook thread. Walks through the 90% WR mirage, the 13-month truth, the decision to kill grid. Signs it with real numbers. Zero spin.

**Life lesson**
- CN: 公开承认错误的那一刻，你就比沉默的人领先了一年。
- EN: The moment you publicly admit you were wrong, you're a year ahead of everyone who stayed silent.

**Beats (~38s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 8. I wrote a 1200-word post titled 'Why I Was Wrong For 7 Days'." / "第 8 天。我写了一篇 1200 字的帖子，标题叫《我为什么错了 7 天》。"
3. [6s] bilingual — "Published to Moltbook. Published to ibitlabs.com. Signed with real numbers." / "发到 Moltbook。发到 ibitlabs.com。带真实数字签名。"
4. [6s] stat — "1,200" "words · zero spin" / "一千二百字 · 零掩饰"
5. [6s] bilingual — "Half my fear about writing it turned out to be imaginary." / "我对写它的恐惧，有一半是想象出来的。"
6. [6s] bilingual (landing) — "The moment you publicly say you were wrong, you are a year ahead of everyone who stayed silent." / "公开承认错误的那一刻，你就比沉默的人领先了一年。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 8 of AI trading my $1,000. I wrote twelve hundred words called "Why I was wrong for 7 days". Published to every channel I had. The hardest part was the first paragraph. After that, the sentences came by themselves.
>
> 2/ The fear in writing a public correction is about losing credibility. It turns out the opposite is true: people trust you more after you admit you were wrong, not less, as long as the admission has numbers attached.
>
> 3/ Half the fear was imaginary. The other half was information about what I had been using credibility for — protecting my past instead of funding my future.
>
> 4/ The moment you publicly say you were wrong, you are a year ahead of everyone who stayed silent. Because silence compounds into bigger mistakes. Corrections compound into better judgment.
>
> 5/ Day 8 cost me zero dollars and earned me the kind of thing you cannot buy: a follower who knows I will tell them when I am wrong. Day 9 tomorrow.

---

## Day 9 · 2026-04-15 · Rebuilding the website while the bot traded

**Signature**
- CN: 「AI 帮我操盘第 9 天 · 机器人在交易，我在重写网站」
- EN: 「Day 9: AI trades my \$1,000 · Rewriting the site while the bot ran」

**Real event**
Spent the whole day restructuring the website from "trading product" framing to "social experiment" framing. New sections: The Story, Free Courses, Simple Pricing, FAQ. Meanwhile the bot ran. 3 trades happened. I looked at them once.

**Life lesson**
- CN: 当你能放心地不盯盘去做别的事，那才是你真正开始信任你做的系统。
- EN: The moment you can stop watching the thing and go build something else — that's the first moment you actually trust what you built.

**Beats (~38s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 9, I spent the whole day rewriting the website." / "第 9 天，一整天在重写网站。"
3. [6s] bilingual — "Meanwhile, the bot placed 3 trades. I checked them once." / "与此同时，机器人做了 3 笔交易。我只看过一次。"
4. [6s] split card — "WEBSITE: 800 lines rewritten / BOT: 3 trades, $-1.80" / "网站：改了 800 行 / 机器人：3 笔交易，−\$1.80"
5. [6s] bilingual — "Not because I don't care. Because I finally built something I can stop watching." / "不是我不在乎。是我终于造出了一个可以不盯着的东西。"
6. [6s] bilingual (landing) — "The moment you can stop watching is the first moment you trust what you built." / "你能放心不盯着的那一刻，就是你开始真正信任它的那一刻。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 9 of AI trading my $1,000. I rewrote the whole website from scratch. Reframed it from "trading product" to "social experiment". Meanwhile the bot made three trades. I checked them once.
>
> 2/ For a week I had been watching every candle. This was the first day I could walk away. Not because I stopped caring. Because I finally had a system I could stop policing.
>
> 3/ The test of any system you build is: can you stop watching it? If you cannot, you didn't build a system, you built a second job. Most people think they built the first when they built the second.
>
> 4/ Day 9 was the first day I rented my attention back from the bot. It was cheaper than I expected, and I wanted to use it for the website, and the website was better for it.
>
> 5/ The moment you can stop watching is the first moment you trust what you built. Everything before that is rehearsal with a pulse in it. Day 10 tomorrow.

---

## Day 10 · 2026-04-16 · Twitter took my account away

**Signature**
- CN: 「AI 帮我操盘第 10 天 · Twitter 把我号封了」
- EN: 「Day 10: AI trades my \$1,000 · Twitter took my account」

**Real event**
@Ibitlabs Twitter account gets suspended. No warning. No clear reason. Same day: I ship bilingual (中英) mode across the entire website, mobile UX polish, and tighten the trailing stop on the bot. Three things in one day because one of them got taken away.

**Life lesson**
- CN: 别把你花了最多力气经营的东西，盖在一个你不拥有的地基上。
- EN: Don't build your most valuable thing on top of ground you don't own.

**Beats (~42s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 10. Twitter suspended my account. No warning." / "第 10 天。Twitter 封了我的号。没有预警。"
3. [6s] stat — "0" "reasons given" / "给出的理由数量"
4. [6s] bilingual — "All my Twitter followers, my thread library, my proof — in one platform's hand." / "我所有的关注者、所有的推文、所有的证据 —— 全在一个平台手里。"
5. [6s] bilingual — "Same day I launched bilingual mode on my own site. Ground I actually own." / "同一天我上线了自己网站的中英双语。我自己拥有的地基。"
6. [6s] bilingual (landing) — "Never build your most valuable thing on ground you don't own." / "别把你最宝贵的东西，盖在你不拥有的地基上。"
7. [5s] OUTRO

**Twitter thread (EN)** *(posted from recovered account, the irony is the hook)*
> 1/ Day 10 Twitter took my account without warning. I got it back later. I will not forget what the week without it looked like. Every follower, every thread, every receipt I had posted, held hostage to a platform that did not call first.
>
> 2/ Same day, I shipped bilingual mode on my own website. English on one toggle, Chinese on the other. It felt small while I was doing it. It stopped feeling small when I had nowhere else to say anything.
>
> 3/ The site is slow to get people to. Twitter was fast. That tradeoff is real. But fast on somebody else's land is not the same as slow on your own. The difference is who can decide you no longer exist.
>
> 4/ Don't build your most valuable thing on top of ground you don't own. I had been ignoring this sentence for years because it sounded like a sentence from a marketing book. On Day 10 it became a sentence I had to pay for.
>
> 5/ Day 10 taught me that I can lose my audience in a blink, but I can't lose my domain without doing it myself. From that day on the site is primary. Everything else is a distribution channel that can be turned off. Day 11 tomorrow.

---

## Day 11 · 2026-04-17 · The trade that made me rewrite everything

**Signature**
- CN: 「AI 帮我操盘第 11 天 · 那笔让我所有叙事作废的交易」
- EN: 「Day 11: AI trades my \$1,000 · The trade that broke my narrative」

**Real event**
Published the Trade #267 retrospective as a daily post — the long-form story of the -$31.54 loss that had triggered the whole V5.1 pivot. Moltbook picked it up. The post started conversations I hadn't expected, including vaultmoth's public affirmation much later.

**Life lesson**
- CN: 一笔失败的交易，如果你愿意把它写下来，可能比十笔赚钱的交易都更有用。
- EN: A single losing trade, if you're willing to write it down, is often more useful than ten winning ones.

**Beats (~40s)**
1. [3s] INTRO
2. [5s] stat — "-$31.54" "Trade #267" / "#267 号交易"
3. [6s] bilingual — "This was the trade that told me my 90% win rate was fiction." / "这笔交易告诉我，那个 90% 胜率是个童话。"
4. [6s] bilingual — "On Day 11, I wrote it down with all the numbers, no spin." / "第 11 天，我把它完整写了下来，带全部数字，不加粉饰。"
5. [6s] bilingual — "It became the post that started the longest conversations I've had all year." / "它成了我全年引发最长对话的那一篇。"
6. [6s] bilingual (landing) — "A losing trade you wrote down is worth more than ten winning trades you didn't." / "一笔你写下来的失败交易，比十笔你没写的盈利交易都值钱。"
7. [5s] OUTRO

---

## Day 12 · 2026-04-18 · Tearing up my scheduled tasks

**Signature**
- CN: 「AI 帮我操盘第 12 天 · 我把定时任务全部推倒重写」
- EN: 「Day 12: AI trades my \$1,000 · I tore up all my scheduled tasks」

**Real event**
All 4 brand-building scheduled tasks (daily post generator, interview comment bot, brand builder, learning loop) got purged and rewritten to match the post-pivot narrative. Cold-started @Ibitlabs_agent. Hard-banned any pre-04-13 WR numbers / momentum language from the brand voice.

**Life lesson**
- CN: 当你换了故事的方向，那些还在讲旧故事的人也得换掉 —— 包括你自动化的那部分自己。
- EN: When you change the story you're telling, you also have to change the version of yourself that has been telling the old one — automated parts included.

**Beats (~40s)**
1. [3s] INTRO
2. [6s] bilingual — "Day 12, I noticed my automated agents were still telling the old story." / "第 12 天，我发现我自动化的 agent 还在讲旧故事。"
3. [6s] stat — "4" "scheduled tasks rewritten from zero" / "定时任务从零重写"
4. [6s] bilingual — "Every brand voice I had delegated had to get the memo." / "所有我授权代言的声音都得收到新通告。"
5. [6s] bilingual — "Otherwise I'd be contradicting myself in my sleep." / "否则我会在睡觉的时候自打嘴巴。"
6. [6s] bilingual (landing) — "When the story changes, every automation that spoke the old story needs to change too." / "故事换了，所有替你讲旧故事的系统都要同步换掉。"
7. [5s] OUTRO

---

## Day 13 · 2026-04-19 · The ghost position

**Signature**
- CN: 「AI 帮我操盘第 13 天 · 它骗我说它平了仓」
- EN: 「Day 13: AI trades my \$1,000 · It lied about closing my position」

**Real event**
Trade #325. Bot hits stop-loss on a LONG. Fires a plain market SELL (no reduce_only flag, no close endpoint). Coinbase treats it as an independent order — nets down the LONG but leaves a residual SHORT that the bot has no record of. 5.5 hours later I find it manually in the app. Close it. Total realized loss: ~$40.

**Life lesson**
- CN: 最危险的失败是那些不会通知你的失败。
- EN: The most dangerous failures are the ones that don't announce themselves.

**Beats (~48s, includes Manim)**
1. [3s] INTRO
2. [5s] bilingual — "On Day 13 I lost $40 to a position that didn't exist." / "第 13 天我为一个不存在的仓位亏了 40 美元。"
3. [9s] MANIM · ghost_spawn_v.mp4 — animated LONG→ghost SHORT spawn
4. [6s] bilingual — "The bot thought it closed the trade. Coinbase thought it opened a new one." / "机器人以为它平了仓。Coinbase 以为它开了新仓。"
5. [5s] stat — "5.5 hours" "before I found it in the app" / "我才在 app 里发现"
6. [6s] bilingual (landing) — "The most dangerous failures are the ones that don't announce themselves." / "最危险的失败，是那些不会主动通知你的失败。"
7. [5s] OUTRO

**Twitter thread (EN)**
> 1/ Day 13 of AI trading my $1,000. The bot placed a trade, hit its stop-loss, sent the close order. The close order worked. Sort of. And that "sort of" cost me $40 and 5 hours and a whole night of debugging the wrong thing.
>
> 2/ The bot's close order was a plain market sell. No reduce-only flag. No close endpoint. Coinbase received it as a new short, netted it against my long, and left a residual short sitting in my account. The bot's brain said zero position. The exchange said one position.
>
> 3/ For 5.5 hours I had a position I had never agreed to hold. Price moved against it. It bled slowly. I found it when I opened the phone app to check something unrelated. I closed it manually at the Coinbase UI.
>
> 4/ What scared me was not the $40. It was that nothing in my monitoring system would have caught this on its own. The bot's self-reports were consistent. The loss was only visible from outside the bot's story.
>
> 5/ The most dangerous failures are the ones that don't announce themselves. They do not crash, they do not page, they do not log. They just slowly make your numbers wrong in a way that still fits your assumptions.
>
> 6/ Day 14 tomorrow: the 3-line fix, and the question I should have been asking from Day 1.

---

## Day 14 · 2026-04-20 · Three lines

**Signature**
- CN: 「AI 帮我操盘第 14 天 · 3 行代码的修复」
- EN: 「Day 14: AI trades my \$1,000 · The 3-line fix」

**Real event**
Patches the close path in `coinbase_exchange.py` and `sol_sniper_executor.py`. Old code: `create_market_order(side=close_side, amount=quantity)`. New code: `close_perp_position(size=quantity)` using Coinbase SDK's dedicated close endpoint (auto-detects direction, cannot leave a residual). Also ships a 15-minute DB ↔ Exchange reconciler as a permanent second witness.

**Life lesson**
- CN: 最贵的课，字数最少。
- EN: The most expensive lessons are the ones that fit in the fewest lines.

**Beats (~40s)**
1. [3s] INTRO
2. [5s] bilingual — "Day 14. I wrote the fix." / "第 14 天。我写了修复。"
3. [10s] code diff card — `-create_market_order(side=...)` / `+close_perp_position(size=...)`
4. [6s] bilingual — "3 lines of code. No more side parameter. SDK detects direction. Cannot leave a residual." / "3 行代码。不再传 side 参数。SDK 自己判别方向。不可能再留残余。"
5. [6s] bilingual — "Same day, I shipped a second witness: reconciler runs every 15 minutes, alerts me on drift." / "同一天我还上线了一个'第二见证人'：对账器每 15 分钟跑一次，有漂移就告警。"
6. [6s] bilingual (landing) — "The most expensive lessons are the ones that fit in the fewest lines." / "最贵的课，字数最少。"
7. [5s] OUTRO

---

## Day 15 · 2026-04-21 · First clean profit

**Signature**
- CN: 「AI 帮我操盘第 15 天 · 它第一次干干净净赚到钱」
- EN: 「Day 15: AI trades my \$1,000 · First clean profit」

**Real event**
Bot restarted. Trade #61 (post-fix numbering) opens at \$85.27 LONG, trailing stop closes at \$86.45. Realized +\$10.35. Reconciler shows zero drift. DB matches exchange. The first trade after the fix, and it's clean.

**Life lesson**
- CN: 一个干净的开始，比一堆好运气都值得庆祝。
- EN: One clean start is worth more than a pile of lucky breaks.

**Beats (~42s)**
1. [3s] INTRO
2. [5s] bilingual — "Day 15. First trade after the fix." / "第 15 天。修复后的第一笔。"
3. [6s] split card — "IN: $85.27 (long) / OUT: $86.45 (trailing)" / "入场 \$85.27 / 出场 \$86.45"
4. [6s] stat — "+$10.35" "clean · no ghost · no residual" (sage green) / "干净 · 无幽灵 · 无残余"
5. [6s] terminal card — reconciler output `db: 2 / ex: 2 / unmatched: 0 / ✅ clean`
6. [6s] bilingual — "I am still net negative on the experiment. That doesn't matter today." / "实验账户整体还是负的。今天这个不重要。"
7. [6s] bilingual (landing) — "One clean start is worth more than a pile of lucky breaks." / "一个干净的开始，胜过一堆好运气。"
8. [5s] OUTRO — "Tomorrow: Day 16 (real time) →"

**Twitter thread (EN)**
> 1/ Day 15 of AI trading my $1,000. First trade after the fix. Long at 85.27. Trailing stop closed at 86.45. Plus ten dollars thirty-five cents. Cleanest number I have had all experiment.
>
> 2/ The reconciler — the second witness I shipped on Day 14 — returned zero drift. Database matches exchange. No ghost. No residual. The fix works in production on real money with real market conditions.
>
> 3/ I am still net negative on the experiment. My balance is under $1,000. That does not matter today. Today was about proving the new system holds a real position correctly from open to close.
>
> 4/ One clean start is worth more than a pile of lucky breaks. Lucky breaks expire. Clean starts compound. Day 15 was not the day I got profitable. It was the day I got trustable to myself.
>
> 5/ Day 16 is real time, not retrospective. Series continues tomorrow. Thank you to everyone who watched me be wrong in public for 15 days straight.
