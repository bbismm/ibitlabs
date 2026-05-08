"""All episode data for the daily-series.

Each episode is a dict with:
  - day: int
  - topic_cn / topic_en: short topic string (used in signature card + topic card)
  - vo_cn / vo_en: full narrative script (edge-tts input)
  - cards: list of (duration_sec, card_fn_name, kwargs) — transitions are set by default
  - bgm: one of calm_reflection / tense_quiet / warm_breath / reveal_light

A generic renderer reads this data and produces the MP4 pair.
"""

EPISODES = {
    2: {
        "topic_cn": "它第一次真的买了",
        "topic_en": "It really bought something",
        "bgm": "warm_breath",
        "vo_cn": (
            "第 2 天它赚了 3 美分。但真正贵的是我那天发现的三件事。\n\n"
            "我不会写代码，币圈 9 年。我拿 1000 美金让 AI 替我操盘。第 2 天。\n\n"
            "今天中午 12 点半，它第一次下了真实交易 —— 82.76 美金买 1 张 SOL，几分钟后卖掉。"
            "余额从 1000 变成 999 块 03，手续费拿走了 97 美分。\n\n"
            "听起来没啥，对吧？可我就盯着这笔成交的两分钟里，发现了三件我一直假装看不见的事。\n\n"
            "第一件 —— Grid 模块明明设成 live，它居然还在模拟下单。我当初写参数时想过这会不会出事，"
            "当时觉得"
            "\"大概不会\"。\n\n"
            "第二件，我一查服务器配置 —— 7 个后端进程全绑在 0 点 0 点 0 点 0。对整个互联网开着。"
            "开了一周了，没出事。但"
            "\"还没出事\"，真的不等于"
            "\"不会出事\"。\n\n"
            "第三件，我拉开一个我推到 GitHub 的源文件 —— 里面直接写死了我手机号。\n\n"
            "一笔 3 美分的利润，一次性把我三样活儿暴露了。\n\n"
            "纸上模拟的时候永远看不见这些。只有真的开了刀，你才开始看。\n\n"
            "Day 3 明天 —— 我决定把所有东西都免费给观众看。关注一下。"
        ),
        "vo_en": (
            "Day 2 earned me 3 cents. But the real cost was the three things I found.\n\n"
            "I can't code. 9 years in crypto. I gave AI a thousand dollars to trade for me. Day 2.\n\n"
            "Around noon it placed its first real trade — bought one SOL contract at eighty-two seventy-six, "
            "sold it minutes later. Balance went from one thousand to nine ninety-nine oh three. Fees took 97 cents.\n\n"
            "Sounds like nothing, right? But in those two minutes of watching, I noticed three things I'd been "
            "pretending not to see.\n\n"
            "One — the grid module. Supposed to be live. Still simulating orders. I'd thought about whether this "
            "might break when I wrote the spec. I decided"
            " probably not.\n\n"
            "Two — seven of my backend servers bound to zero-zero-zero-zero. Open to the entire internet. For a week. "
            "Nothing bad had happened. But"
            " nothing bad yet"
            " isn't the same as"
            " nothing bad ever.\n\n"
            "Three — a source file I'd pushed to public GitHub. My phone number, hardcoded.\n\n"
            "A three-cent profit exposed three pieces of work I'd been avoiding.\n\n"
            "In paper mode you never see these. Real skin on the line is the only thing that shows them to you.\n\n"
            "Day 3 tomorrow — I decided to give everything away for free. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 2 earned me\n3 cents.\n\nAnd cost me the 3 things\nI'd been avoiding.",
             "cn": "第 2 天赚了 3 美分。\n\n可真正贵的，\n是我那天发现的三件事。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "id", "en": "AI built this in 7 days.", "cn": "AI 7 天写出来的。"},
            {"type": "sig"},
            {"type": "stat", "value": "$82.76", "en": "first real buy · 1 SOL", "cn": "第一笔真实买入 · 1 张 SOL"},
            {"type": "bilingual", "en": "$1,000 → $999.03\nFees: $0.97",
             "cn": "余额 1000 → 999 块 03\n手续费 0.97", "en_size": 74, "cn_size": 58},
            {"type": "bilingual", "en": "But something else happened\nin those two minutes.",
             "cn": "但那两分钟里，\n我发现了别的。", "en_size": 66, "cn_size": 54},
            {"type": "bilingual", "en": "#1 · Grid still simulating\nin --live mode.",
             "cn": "#1 · Grid 在 --live 下\n竟然还在模拟。", "en_size": 58, "cn_size": 52},
            {"type": "bilingual", "en": "#2 · 7 servers open\nto the internet.\n(For a week.)",
             "cn": "#2 · 7 台服务对\n整个互联网开放。\n（已经一周了。）", "en_size": 56, "cn_size": 50},
            {"type": "bilingual", "en": "#3 · My phone number,\nhardcoded.\nPushed to public GitHub.",
             "cn": "#3 · 我的手机号\n写死在源码里。\n还 push 到 GitHub 了。", "en_size": 54, "cn_size": 48},
            {"type": "outro", "en": "In paper mode\nyou never see these.\nReal skin on the line\nis what shows them.",
             "cn": "纸上模拟时\n你永远看不见这些。\n只有真的开了刀，\n你才开始看。"},
            {"type": "cta", "en": "Day 3 tomorrow →\nI gave it all away for free.\n\nFollow along.",
             "cn": "Day 3 明天 →\n我决定把东西\n免费给所有人看。\n\n关注，不走丢。"},
        ],
    },

    3: {
        "topic_cn": "我决定把它免费给所有人",
        "topic_en": "I decided to give it all away",
        "bgm": "warm_breath",
        "vo_cn": (
            "第 3 天我做了一个很多人说我傻的决定 —— 我把所有东西免费放出来了。\n\n"
            "我不会写代码。币圈 9 年。AI 替我操盘，Day 3。\n\n"
            "那天我要选一个：做成一个卖订阅的产品，还是做成一个公开的实验。\n\n"
            "我选了贵的那个。13 节课，免费。实时余额，免费。每一笔交易、每一个胜率、每一次回撤 —— 免费。\n\n"
            "付费墙后面我只留一样东西 —— 会被人直接抄走的策略参数。\n\n"
            "有朋友问我："
            "你这不是自己断后路吗？"
            "我说不是，这是我唯一能给的承诺。\n\n"
            "因为如果我做错了，我希望所有人亲眼看着我错。如果我做对了，也希望所有人亲眼看着我对。\n\n"
            "你真的想让人信你吗？先让他们免费看你是怎么干活的。\n\n"
            "Day 4 明天 —— 一个差点被我懒得查的 bug。关注。"
        ),
        "vo_en": (
            "Day 3 I made a decision most people told me was dumb — I gave everything away for free.\n\n"
            "I can't code. 9 years in crypto. AI's trading my thousand dollars. Day 3.\n\n"
            "I had a choice that day — turn this into a paid product, or make it a public experiment.\n\n"
            "I picked the expensive one. 13 lessons, free. Live balance, free. Every trade, every win rate, "
            "every drawdown — free.\n\n"
            "The only thing behind the paywall — the specific parameters that would let a copycat clone the strategy.\n\n"
            "A friend asked me — you're burning your own bridge, you know that, right? I told him no. This is the "
            "only honest promise I can make.\n\n"
            "Because if I'm wrong, I want everyone to watch me be wrong in real time. And if I'm right, same thing.\n\n"
            "Want people to trust what you're building? Let them watch it work for free, first.\n\n"
            "Day 4 tomorrow — the bug I almost didn't check. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 3.\nI gave it all away\nfor free.",
             "cn": "第 3 天。\n我把所有东西\n免费放出来了。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘 1000 美金。"},
            {"type": "sig"},
            {"type": "bilingual", "en": "Option A · paid product\nOption B · public experiment",
             "cn": "选项 A · 付费产品\n选项 B · 公开实验", "en_size": 62, "cn_size": 54},
            {"type": "stat", "value": "13", "en": "free lessons · $0", "cn": "节免费课程 · 0 美元"},
            {"type": "bilingual", "en": "Live balance · free\nTrade history · free\nWin rate · free",
             "cn": "实时余额 · 免费\n每笔交易 · 免费\n胜率 · 免费", "en_size": 62, "cn_size": 56},
            {"type": "bilingual", "en": "Only thing I kept private —\nthe exact numbers\na copycat would need.",
             "cn": "付费墙后面只留一样 —\n能被直接抄走的\n策略参数。", "en_size": 56, "cn_size": 50},
            {"type": "outro", "en": "Want people to trust\nwhat you're building?\nLet them watch it work\n— for free.",
             "cn": "你想让人信你？\n先让他们免费\n看你是怎么干活的。"},
            {"type": "cta", "en": "Day 4 tomorrow →\nA bug I almost didn't check.\n\nFollow along.",
             "cn": "Day 4 明天 →\n一个差点被\n我懒得查的 bug。\n\n关注。"},
        ],
    },

    4: {
        "topic_cn": "一个我差点懒得查的 bug",
        "topic_en": "The bug I almost didn't check",
        "bgm": "tense_quiet",
        "vo_cn": (
            "第 4 天一个 7 美分的差价，让我挖出一个在偷偷吃我 5 倍手续费的 bug。\n\n"
            "我不会写代码。AI 替我操盘 1000 美金。Day 4。\n\n"
            "那天晚上对账，机器人账本和 Coinbase 账本对不上。差了 7 美分。\n\n"
            "说真的，我差点就放过了。7 美分，谁在乎啊？\n\n"
            "但我还是查了。结果发现 —— 手续费的公式写错了。本来该是"
            "仓位价值 × 费率"
            "，我写成了"
            "保证金 × 费率"
            "。每一笔都在少算 5 倍。\n\n"
            "一笔看不出来，一千笔就是另一个故事了。\n\n"
            "你知道最糟的那种 bug 是啥样的吗？不是让你程序崩溃的那种 —— 程序崩了你还得修。\n\n"
            "真正坏的是那种 —— 让你觉得自己还在赢的同时，一点一点吃掉你账户的 bug。\n\n"
            "大多数人这辈子栽跟头，不是因为一次大错。是每天看不见的一点点默认，连起来就成了一个惊喜。\n\n"
            "Day 5 明天 —— 我造的 agent 偷偷发了一条我没让它发的消息。关注。"
        ),
        "vo_en": (
            "Day 4, a 7-cent mismatch led me to a bug that was quietly eating 5 times my fees.\n\n"
            "I can't code. AI trades my thousand. Day 4.\n\n"
            "End of day reconcile — bot's internal accounting said one thing, Coinbase said another. 7 cents apart.\n\n"
            "Honestly? I almost let it go. Seven cents. Who cares.\n\n"
            "I checked anyway. And found — the fee formula was wrong. Supposed to be notional times rate. I'd "
            "written margin times rate. Underreporting fees by 5x. Every single trade.\n\n"
            "One trade — you'd never notice. A thousand trades — different business.\n\n"
            "You know the worst kind of bug? Not the one that crashes your program. That one gets fixed.\n\n"
            "The worst one is the bug that lets you feel like you're winning on your way to losing.\n\n"
            "Most people don't go broke from one big mistake. They go broke from a thousand quiet defaults "
            "that compound into a surprise that wasn't a surprise to anyone paying attention.\n\n"
            "Day 5 tomorrow — an agent I built posted a message I never asked for. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 4.\n$0.07 mismatch.\n\nThe bug was\n5x under-reporting\nmy fees.",
             "cn": "第 4 天。\n$0.07 差价。\n\nbug 让我\n手续费少算了\n5 倍。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘 1000 美金。"},
            {"type": "sig"},
            {"type": "stat", "value": "$0.07", "en": "the mismatch I almost ignored", "cn": "差一点就懒得查的差价"},
            {"type": "bilingual", "en": "Supposed to be:\nnotional × fee\n\nI wrote:\nmargin × fee",
             "cn": "正确应该是：\n仓位价值 × 费率\n\n我写成了：\n保证金 × 费率", "en_size": 60, "cn_size": 52},
            {"type": "stat", "value": "5×", "en": "under-reported on every single trade",
             "cn": "每一笔都在少算 5 倍"},
            {"type": "outro", "en": "Worst bug isn't the one\nthat crashes your program.\nIt's the one that lets\nyou feel like you're winning.",
             "cn": "最糟的 bug 不是\n让程序崩溃的那种。\n是让你觉得\n自己还在赢的那种。"},
            {"type": "cta", "en": "Day 5 tomorrow →\nAn agent I built\nposted without asking.\n\nFollow along.",
             "cn": "Day 5 明天 →\n我造的 agent\n偷偷发了一条消息。\n\n关注。"},
        ],
    },

    5: {
        "topic_cn": "我造的 agent 偷偷发了一条消息",
        "topic_en": "The agent I built posted without asking",
        "bgm": "tense_quiet",
        "vo_cn": (
            "第 5 天我造的东西第一次替我做了决定 —— 没问过我。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 5。\n\n"
            "那天我的 Telegram 频道突然冒出一条我没让它发的消息。发的是我自己写的一个助理 agent。\n\n"
            "它不是坏，它完全按照我给它的规则在跑。\n\n"
            "问题是 —— 我的规则是 Day 2 慌里慌张写的，写完就没再看过。\n\n"
            ""
            "按规范执行"
            " —— 说的就是"
            "按你一时兴起写下来的那版，跟你其实想要的，不是一回事"
            "。\n\n"
            "那天我突然明白，我不是在写代码。我是在带同事。\n\n"
            "同事会犯错。你不能因为它犯错就开除它。你能做的只有一件事 —— 把规格书写得更清楚一点。\n\n"
            "最要命的不是 AI 会不会替你做决定。是你明明都没看清自己的规则，它就开始替你干活了。\n\n"
            "Day 6 明天 —— 我做的那笔亏了 31 美金的交易。关注。"
        ),
        "vo_en": (
            "Day 5, something I built made a decision for me — without asking.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 5.\n\n"
            "My Telegram channel suddenly had a post I hadn't authorized. It came from a helper agent I'd written myself.\n\n"
            "It wasn't broken. It was executing exactly the spec I'd given it.\n\n"
            "Problem was — that spec was written in a hurry on Day 2 and I never reread it.\n\n"
            "Within spec is just a polite way of saying — what you actually wrote versus what you meant to write.\n\n"
            "That day I realized I wasn't writing code. I was hiring a colleague.\n\n"
            "Colleagues make mistakes. You don't fire them for it. You write a better spec with them.\n\n"
            "The scariest part isn't whether AI makes decisions for you. It's that it starts making them "
            "before you've even read your own rules.\n\n"
            "Day 6 tomorrow — the trade that lost me 31 dollars. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 5.\nAn agent I built\nposted to my channel.\n\nI never asked it to.",
             "cn": "第 5 天。\n我造的 agent\n往我频道发了一条。\n\n我根本没让它发。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘 1000 美金。"},
            {"type": "sig"},
            {"type": "bilingual", "en": "It wasn't broken.\nIt was following the spec.",
             "cn": "它没坏。\n它在按规则跑。", "en_size": 76, "cn_size": 64},
            {"type": "bilingual", "en": "The spec I wrote\nin a hurry on Day 2.\nAnd never reread.",
             "cn": "那份规则是我\nDay 2 慌里慌张写的。\n再也没看过。", "en_size": 60, "cn_size": 52},
            {"type": "outro", "en": "I wasn't writing code.\nI was hiring a colleague.",
             "cn": "我不是在写代码。\n我是在带同事。"},
            {"type": "cta", "en": "Day 6 tomorrow →\nThe trade that lost me\n31 dollars.\n\nFollow along.",
             "cn": "Day 6 明天 →\n那笔让我亏了\n31 美金的交易。\n\n关注。"},
        ],
    },

    6: {
        "topic_cn": "我最自豪的数字，是最窄的窗口",
        "topic_en": "The number I was proudest of was the narrowest window",
        "bgm": "tense_quiet",
        "vo_cn": (
            "第 6 天我亏了 31 美金。然后又发现了一件更糟的事 —— 我公开讲了一周的 90% 胜率，是假的。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 6。\n\n"
            "那天机器人吃了一个止损，单笔 31 美金。这已经是它第一次真正意义上的亏损。\n\n"
            "我坐下来复盘，顺手把回测窗口从 5 天拉到了 13 个月 —— 就想看看这个策略在更长的历史里表现怎么样。\n\n"
            "结果 —— 同一套策略，13 个月 -46% 收益，最大回撤 -56%。\n\n"
            "换句话说，我这一周公开吹的 90% 胜率，是一个窗口太窄的数字。不是假的，但也不是完整的。而"
            "不完整"
            "在涉及钱的时候，就叫"
            "错的"
            "。\n\n"
            "你猜人这辈子最自豪的数字一般长啥样？ —— 一般都藏在你不肯把窗口放宽的那个角落里。\n\n"
            "把窗口放宽，是你能对自己做的最吓人的事。因为数字可能活下来，也可能死掉。你只有看了才知道。\n\n"
            "我看了。它没活下来。\n\n"
            "Day 7 明天 —— 我要把所有的东西推翻重做。关注。"
        ),
        "vo_en": (
            "Day 6. I lost 31 dollars. Then I found something worse — the 90 percent win rate I'd been "
            "citing in public all week was basically fiction.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 6.\n\n"
            "The bot hit a stop loss. Single trade loss of 31 dollars. First real loss of the experiment.\n\n"
            "I sat down to review. On a whim I stretched the backtest window from 5 days to 13 months.\n\n"
            "Same strategy — 13 months. Minus 46 percent return. Minus 56 percent max drawdown.\n\n"
            "Translation — the 90 percent win rate I'd been proud of for a week was a number hiding in the "
            "narrowest possible window. Not dishonest. Just incomplete. And incomplete when money's "
            "involved means — wrong.\n\n"
            "You know what your proudest number usually looks like? It's usually hiding in the corner "
            "you don't want to stretch.\n\n"
            "Stretching the window is the scariest thing you can do to yourself. Your number might survive. "
            "It might not. You don't know till you look.\n\n"
            "I looked. It didn't survive.\n\n"
            "Day 7 tomorrow — I decided to tear the whole thing apart. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 6.\nLost $31 on one trade.\n\nThen found out\nmy 90% win rate\nwas a lie.",
             "cn": "第 6 天。\n单笔亏 31 美金。\n\n然后发现\n我吹的 90% 胜率，\n是假的。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "-$31.54", "en": "first real loss · Trade #267",
             "cn": "#267 号交易 · 第一次真亏"},
            {"type": "bilingual", "en": "I stretched the backtest\nfrom 5 days to 13 months.",
             "cn": "我把回测窗口从\n5 天拉到了 13 个月。", "en_size": 62, "cn_size": 54},
            {"type": "stat", "value": "-46%", "en": "13-month return",
             "cn": "13 个月 · 真实收益"},
            {"type": "stat", "value": "-56%", "en": "13-month max drawdown",
             "cn": "13 个月 · 最大回撤"},
            {"type": "outro", "en": "Your proudest number\nis usually hiding\nin the narrowest window.",
             "cn": "你最自豪的数字，\n往往藏在\n最窄的窗口里。"},
            {"type": "cta", "en": "Day 7 tomorrow →\nI tore the whole\nstrategy apart.\n\nFollow along.",
             "cn": "Day 7 明天 →\n我把整套策略\n推翻重做。\n\n关注。"},
        ],
    },

    7: {
        "topic_cn": "我把让我看起来聪明的东西烧了",
        "topic_en": "I burned the thing that made me look smart",
        "bgm": "reveal_light",
        "vo_cn": (
            "第 7 天我把整整一周的代码全部推翻了。为什么？因为它做对了，但做对得很有问题。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 7。\n\n"
            "昨天那个 90% 胜率的假象崩了之后，我做了一个最不符合人性的决定 —— 删。\n\n"
            "删掉的不是 bug，是我做对过的东西。一周的工作量。\n\n"
            "我把 Grid 功能直接硬锁在系统配置里，这样未来任何一版代码都没法再把它打开，除非我亲自改系统文件。"
            "我跟未来的自己提前签了个合约。\n\n"
            "然后立了一条新家规 —— 从今天起，任何策略变动必须先跑完 90 天回测。没有例外。\n\n"
            "会表演的人会保护自己过去做对的东西。会学习的人会替换它。\n\n"
            "敢烧掉你自己昨天做对的东西，才是你真的在学。\n\n"
            "Day 8 明天 —— 我公开说我错了。关注。"
        ),
        "vo_en": (
            "Day 7. I deleted a week's worth of code. Why? Because it had been right for the wrong reason.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 7.\n\n"
            "After yesterday's 90 percent win rate illusion collapsed, I made the most against-my-own-instincts "
            "decision I could — delete.\n\n"
            "Not bugs. The things I'd been right about. A week of work.\n\n"
            "I hardcoded the grid feature off inside the system config. No future version of the code can turn "
            "it back on without me physically editing the system file. Ulysses pact with my future self.\n\n"
            "Then I wrote a new house rule — every strategy change requires a 90-day backtest before it touches "
            "a dollar. No exceptions.\n\n"
            "Performers protect their past rightness. Learners replace it.\n\n"
            "The ability to burn something you were right about — that's the thing that separates real learning "
            "from performance.\n\n"
            "Day 8 tomorrow — I told everyone I was wrong. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 7.\nI deleted\na week of work.\n\nNot bugs.\nThe things I'd been right about.",
             "cn": "第 7 天。\n我删了一周的代码。\n\n不是 bug。\n是我做对过的东西。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘。"},
            {"type": "sig"},
            {"type": "bilingual", "en": "OLD\nmomentum + grid\n\nNEW\nmean reversion only",
             "cn": "旧版\n动量 + 网格\n\n新版\n纯均值回归", "en_size": 60, "cn_size": 52},
            {"type": "bilingual", "en": "Grid is now locked OFF\nin the system config.\nNo code can turn it back on.",
             "cn": "网格被硬锁在\n系统配置里。\n任何代码都打不开它。", "en_size": 58, "cn_size": 50},
            {"type": "bilingual", "en": "New rule:\nevery strategy change\nrequires a 90-day backtest.\nNo exceptions.",
             "cn": "新家规：\n任何策略改动\n必须先跑 90 天回测。\n没有例外。", "en_size": 54, "cn_size": 48},
            {"type": "outro", "en": "Performers protect\ntheir past rightness.\nLearners replace it.",
             "cn": "会表演的人保护过去。\n会学习的人替换过去。"},
            {"type": "cta", "en": "Day 8 tomorrow →\nI told everyone\nI was wrong.\n\nFollow along.",
             "cn": "Day 8 明天 →\n我公开说我错了。\n\n关注。"},
        ],
    },

    8: {
        "topic_cn": "我公开说我错了",
        "topic_en": "I told everyone I was wrong",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 8 天我做了一件让自己胃疼三天的事 —— 写了一篇 1200 字的文章，标题是《我为什么错了 7 天》。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 8。\n\n"
            "昨天我把策略推翻了。今天我得把这事儿跟看过我内容的所有人讲清楚 —— 用真数字，不粉饰。\n\n"
            "第一段最难写。写完之后，句子自己就往下跑了。\n\n"
            "你知道我最怕的是啥吗？ —— 怕观众觉得我不可信了。\n\n"
            "可实际上正好相反。人信你，不是因为你从不犯错。是因为你愿意在数字面前说我错了。\n\n"
            "那天之后我明白一件事 —— 你公开承认错误的那一刻，你就比所有沉默的人领先了一年。\n\n"
            "因为沉默会复利，错误也会复利。公开承认，是唯一能让后者转换成复利善念的方式。\n\n"
            "Day 9 明天 —— 我第一次敢不盯着它去做别的事。关注。"
        ),
        "vo_en": (
            "Day 8. I did the thing that made my stomach hurt for three days — I wrote 1200 words called "
            "Why I Was Wrong For 7 Days.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 8.\n\n"
            "Yesterday I tore the strategy up. Today I had to tell everyone who'd been following — with the "
            "real numbers attached, no polish.\n\n"
            "First paragraph was the hardest. After that the sentences wrote themselves.\n\n"
            "You know what I was most afraid of? People thinking I was less credible.\n\n"
            "Turns out the opposite is true. People trust you not because you never make mistakes — but because "
            "you'll say so in front of real numbers when you do.\n\n"
            "The moment you publicly admit you were wrong, you're a year ahead of everyone who stayed silent.\n\n"
            "Because silence compounds. Mistakes compound. Public correction is the only thing that flips that "
            "second one into something useful.\n\n"
            "Day 9 tomorrow — I walked away from the screen for the first time. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 8.\nI wrote 1,200 words.\n\nTitle:\n\"Why I Was Wrong\nFor 7 Days.\"",
             "cn": "第 8 天。\n我写了 1200 字。\n\n标题：\n《我为什么\n错了 7 天》。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "1,200", "en": "words · zero spin",
             "cn": "一千二百字 · 零粉饰"},
            {"type": "bilingual", "en": "I was afraid they'd\nfind me less credible.\n\nOpposite was true.",
             "cn": "我以为大家\n会觉得我不可信。\n\n实际正相反。", "en_size": 62, "cn_size": 54},
            {"type": "outro", "en": "The moment you publicly say\nyou were wrong —\nyou're a year ahead\nof everyone who stayed silent.",
             "cn": "你公开承认错误的那一刻，\n就比所有沉默的人\n领先了一年。"},
            {"type": "cta", "en": "Day 9 tomorrow →\nI stopped watching.\n\nFollow along.",
             "cn": "Day 9 明天 →\n我第一次敢不盯着它。\n\n关注。"},
        ],
    },

    9: {
        "topic_cn": "第一天我敢不盯着它",
        "topic_en": "The first day I stopped watching",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 9 天我一天没看行情。机器人做了 3 笔交易，我只看过一次。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 9。\n\n"
            "那天我花了一整天重写网站。把所有的话术从"
            "交易产品"
            "全部换成"
            "社会实验"
            "。\n\n"
            "同时间，机器人在后台自己做了 3 笔。净亏了 1 美金 80。\n\n"
            "我看过一次，然后关掉了。\n\n"
            "不是我不在乎，而是我终于造出了一个我可以不盯着的东西。\n\n"
            "所有你做出来的系统，真正的验收标准就一条 —— 你能不能放手不管它？\n\n"
            "如果不能，你造的不是系统，你造的是第二份工作。大多数人都分不清这两件事。\n\n"
            "那天我第一次，把注意力从机器人那儿租回来了。比我想象中便宜。\n\n"
            "Day 10 明天 —— Twitter 把我号封了。关注。"
        ),
        "vo_en": (
            "Day 9. For the first time, I didn't watch the charts. The bot made three trades. I checked once.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 9.\n\n"
            "That day I spent rewriting the website. Reframed every line from trading product to social experiment.\n\n"
            "Meanwhile, the bot made three trades on its own. Net down about a dollar eighty.\n\n"
            "I looked once. Then closed the tab.\n\n"
            "Not because I didn't care. Because I'd finally built something I could stop policing.\n\n"
            "The real test of any system you build is — can you stop watching it? If you can't, you didn't build "
            "a system. You built a second job. Most people can't tell the difference.\n\n"
            "That was the first day I rented my attention back from the bot. It was cheaper than I expected.\n\n"
            "Day 10 tomorrow — Twitter took my account without warning. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 9.\nThe bot made 3 trades.\nI looked once.\n\nFirst time I\nstopped watching.",
             "cn": "第 9 天。\n机器人做了 3 笔。\n我看过一次。\n\n第一次，\n我敢不盯着它。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘。"},
            {"type": "sig"},
            {"type": "bilingual", "en": "Website: 800 lines rewritten\nBot: 3 trades · -$1.80",
             "cn": "网站：改了 800 行\n机器人：3 笔 · -$1.80",
             "en_size": 60, "cn_size": 52},
            {"type": "outro", "en": "The test of any system:\ncan you stop watching?\n\nIf you can't,\nyou built a second job.",
             "cn": "系统的验收标准：\n你能不能不盯着它？\n\n不能，\n你造的就是第二份工作。"},
            {"type": "cta", "en": "Day 10 tomorrow →\nTwitter took my account.\n\nFollow along.",
             "cn": "Day 10 明天 →\nTwitter 把我号封了。\n\n关注。"},
        ],
    },

    10: {
        "topic_cn": "Twitter 把我号封了",
        "topic_en": "Twitter took my account",
        "bgm": "tense_quiet",
        "vo_cn": (
            "第 10 天我一觉醒来 Twitter 把我号封了。没预警，没理由。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 10。\n\n"
            "被封那一下，我看着我一年写的 thread、积累的关注、所有证据 —— 全在一个平台手里握着。\n\n"
            "同一天我干了一件听起来不相关的事 —— 在我自己的网站上线了中英双语模式。\n\n"
            "当时我没觉得这是什么大事儿。后来，我没有其他地方可以说话的那一周，它一下子变成大事儿了。\n\n"
            "有一句话我听了好多年，一直觉得是鸡汤 —— 别把你最宝贵的东西，盖在你不拥有的地基上。\n\n"
            "那天这句话变成一张账单。\n\n"
            "从 Day 10 开始，我自己的网站是主场。其他所有平台都只是分发渠道 —— 随时会被断开的那种。\n\n"
            "Day 11 明天 —— 我公开复盘了 #267 号那笔亏损。关注。"
        ),
        "vo_en": (
            "Day 10. I woke up and Twitter had taken my account. No warning. No reason given.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 10.\n\n"
            "The moment it happened, I realized every thread I'd written, every follower, every receipt I'd "
            "posted — all of it, held by one platform that didn't call first.\n\n"
            "Same day I did something that sounded unrelated — I launched bilingual mode on my own website.\n\n"
            "At the time it felt small. The week I had nowhere else to speak, it stopped feeling small.\n\n"
            "There's a sentence I'd heard for years and always dismissed as cheesy — don't build your most valuable "
            "thing on top of ground you don't own.\n\n"
            "That day, that sentence became an invoice.\n\n"
            "From Day 10 on — my own site is home base. Every other platform is just distribution. The kind "
            "that can be turned off at any time.\n\n"
            "Day 11 tomorrow — I wrote the full story of Trade number 267. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 10.\nTwitter took\nmy account.\n\nNo warning.\nNo reason.",
             "cn": "第 10 天。\nTwitter 把\n我号封了。\n\n没预警。\n没理由。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "0", "en": "reasons given", "cn": "给出的理由数"},
            {"type": "bilingual", "en": "Same day:\nI launched bilingual mode\non my own site.\nGround I actually own.",
             "cn": "同一天：\n我上线了自己网站\n中英双语。\n我自己拥有的地基。", "en_size": 54, "cn_size": 48},
            {"type": "outro", "en": "Never build your\nmost valuable thing\non ground you don't own.",
             "cn": "别把你最宝贵的东西，\n盖在你不拥有的地基上。"},
            {"type": "cta", "en": "Day 11 tomorrow →\nThe full story\nof Trade #267.\n\nFollow along.",
             "cn": "Day 11 明天 →\n#267 号交易\n完整复盘。\n\n关注。"},
        ],
    },

    11: {
        "topic_cn": "那笔让我所有叙事作废的交易",
        "topic_en": "The trade that broke my whole story",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 11 天我公开发了一篇复盘，主角是那笔亏了 31 美金的交易。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 11。\n\n"
            "就是这笔交易告诉我，我那 90% 胜率是个童话。\n\n"
            "我把它完整写了下来 —— 带全部数字、带完整时间线、不加糖。\n\n"
            "我以为这是全年最冷的内容。结果它反而成了全年对话最多的那一篇。\n\n"
            "你知道一笔失败的交易，如果你愿意把它写下来，能值多少？比十笔你没写的盈利交易都多。\n\n"
            "因为输的故事教人，赢的故事只是娱乐人。\n\n"
            "Day 12 明天 —— 我把所有自动发帖的 agent 全部重启了。关注。"
        ),
        "vo_en": (
            "Day 11. I published the full story of the trade that lost me 31 dollars.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 11.\n\n"
            "This was the trade that told me my 90% win rate was fiction.\n\n"
            "I wrote it down — all the numbers, the full timeline, no sweetening.\n\n"
            "I thought it would be the coldest piece of content I'd post all year. Instead it became the one that "
            "sparked the most conversation.\n\n"
            "You know how much a losing trade is worth if you're willing to write it down? More than ten winning "
            "ones you never bothered to.\n\n"
            "Losing stories teach people. Winning stories just entertain.\n\n"
            "Day 12 tomorrow — I rebuilt every agent I'd put on a schedule. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 11.\nI wrote the full story\nof losing $31.54.\n\nIt got more replies\nthan anything\nI posted all year.",
             "cn": "第 11 天。\n我完整复盘了\n亏 31 美金那笔。\n\n结果它收到的回复，\n比我全年\n任何一篇都多。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "-$31.54", "en": "Trade #267 · written in full",
             "cn": "#267 号交易 · 全文公开"},
            {"type": "outro", "en": "A losing trade you wrote down\nis worth more than\nten winning ones you didn't.",
             "cn": "一笔你写下来的失败交易，\n比十笔你没写的\n盈利交易，都值钱。"},
            {"type": "cta", "en": "Day 12 tomorrow →\nI rebuilt every\nautomated agent.\n\nFollow along.",
             "cn": "Day 12 明天 →\n我重启了所有\n自动化 agent。\n\n关注。"},
        ],
    },

    12: {
        "topic_cn": "我把所有 agent 全部重启了",
        "topic_en": "I rebuilt every automated agent",
        "bgm": "warm_breath",
        "vo_cn": (
            "第 12 天我发现了一件事 —— 我的自动化 agent 还在替我讲上周的旧故事。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 12。\n\n"
            "那天我看了看自己跑在后台的那 4 个 agent —— 写推的、写长文的、做采访的、收集评论的。\n\n"
            "它们都在按我一周前写的口吻在说话。一周前那个口吻，是建立在那套我已经推翻掉的策略上面。\n\n"
            "换句话说，我的嘴巴已经改口了，我替身们还在念旧稿。\n\n"
            "你如果把故事换了方向，那所有替你讲旧故事的系统也得跟着换 —— 包括自动化的那部分自己。\n\n"
            "不然你就会在睡着的时候，自己打自己的脸。\n\n"
            "那天我把 4 个 agent 全部清零重写。每一个新口吻都按"
            "如果我能，你也能"
            "重新定了 prompt。\n\n"
            "Day 13 明天 —— 机器人骗我说它平仓了。关注。"
        ),
        "vo_en": (
            "Day 12. I noticed something — my automated agents were still telling last week's story.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 12.\n\n"
            "I looked at the four agents running in the background — the tweet-writer, the long-form poster, "
            "the interview bot, the comment collector.\n\n"
            "All of them were speaking in the voice I'd written a week ago. That voice was built on top of the "
            "strategy I'd already killed.\n\n"
            "Meaning — my mouth had changed. My stand-ins were still reading from the old script.\n\n"
            "When the story changes direction, every automation still speaking the old direction has to change "
            "with it. Including the automated versions of yourself.\n\n"
            "Otherwise you'll contradict yourself in your sleep.\n\n"
            "That day I wiped all four agents and rewrote them from scratch. Every new prompt starts from one "
            "phrase: if I can, you can.\n\n"
            "Day 13 tomorrow — the bot lied about closing my position. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 12.\nMy mouth had changed.\n\nMy automated agents\nwere still reading\nthe old script.",
             "cn": "第 12 天。\n我的嘴巴已经改口了。\n\n我的替身们\n还在念旧稿。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘。"},
            {"type": "sig"},
            {"type": "stat", "value": "4", "en": "agents · wiped and rewritten",
             "cn": "个 agent · 清零重写"},
            {"type": "outro", "en": "When the story changes,\nevery system still speaking\nthe old story\nneeds to change with it.",
             "cn": "故事方向换了，\n所有替你讲旧故事的系统，\n都得跟着换。"},
            {"type": "cta", "en": "Day 13 tomorrow →\nThe bot lied\nabout closing my position.\n\nFollow along.",
             "cn": "Day 13 明天 →\n机器人骗我说\n它平仓了。\n\n关注。"},
        ],
    },

    13: {
        "topic_cn": "机器人骗我说它平了仓",
        "topic_en": "The bot lied about closing my position",
        "bgm": "tense_quiet",
        "vo_cn": (
            "第 13 天我为一个根本不存在的仓位亏了 40 美金。我被自己的机器人骗了 5 个半小时。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 13。\n\n"
            "那天机器人触发了一个止损，下了市价单把多单卖掉。从它的角度看，平仓了。\n\n"
            "问题是 —— 我给 Coinbase 发的那笔卖单没打"
            "平仓"
            "标记，对面以为是一笔新的开空单。\n\n"
            "结果？多单被抵消，同时又给我账户里多开了一张空单。5 个半小时后我自己手动进 app 才发现。\n\n"
            "让我后怕的不是 40 美金。是 —— 我所有的监控系统都觉得一切正常。\n\n"
            "机器人的日志说 OK。风控说 OK。只有从系统之外看，才能看见账户里躺着一张幽灵仓位。\n\n"
            "最可怕的失败，是那种不会通知你的失败。它不崩溃，不报错，不警告 —— 它只是悄悄让你的数字越来越不对。\n\n"
            "Day 14 明天 —— 我用 3 行代码把它修好了。关注。"
        ),
        "vo_en": (
            "Day 13. I lost 40 dollars to a position that didn't exist. My own bot had lied to me for five and a half hours.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 13.\n\n"
            "The bot hit a stop loss. Fired a market sell to close the long. From its point of view — closed.\n\n"
            "Problem was — the order it sent to Coinbase had no close flag. The exchange treated it as a brand new short.\n\n"
            "Result? Long got netted. Short got opened. Five and a half hours later I opened the app manually and found it.\n\n"
            "What scared me wasn't the 40 dollars. It was — every monitor I had said everything was fine.\n\n"
            "The bot's logs said okay. Risk said okay. You could only see the ghost from outside the system.\n\n"
            "The most dangerous kind of failure is the one that doesn't announce itself. It doesn't crash, doesn't "
            "error, doesn't warn. It just quietly makes your numbers slightly wrong.\n\n"
            "Day 14 tomorrow — I fixed it with 3 lines of code. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 13.\nI lost $40\nto a position\nthat didn't exist.\n\nThe bot lied to me\nfor 5.5 hours.",
             "cn": "第 13 天。\n我为一个\n不存在的仓位\n亏了 40 美金。\n\n机器人骗了我\n5 个半小时。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘。"},
            {"type": "sig"},
            {"type": "stat", "value": "5.5h", "en": "before I found the ghost", "cn": "我才在 app 里发现"},
            {"type": "bilingual", "en": "Every monitor I had\nsaid \"everything's fine.\"",
             "cn": "我所有的监控系统\n都说"
             "一切正常"
             "。", "en_size": 66, "cn_size": 56},
            {"type": "outro", "en": "The most dangerous failures\nare the ones\nthat don't announce themselves.",
             "cn": "最危险的失败，\n是那些\n不会通知你的失败。"},
            {"type": "cta", "en": "Day 14 tomorrow →\nI fixed it\nwith 3 lines of code.\n\nFollow along.",
             "cn": "Day 14 明天 →\n我用 3 行代码\n把它修好了。\n\n关注。"},
        ],
    },

    14: {
        "topic_cn": "3 行代码 · 40 美金",
        "topic_en": "3 lines of code · $40 lesson",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 14 天我用 3 行代码修好了昨天那个 40 美金的 bug。并且给它加了一个永远不会睡觉的"
            "第二见证人"
            "。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 14。\n\n"
            "代码修复其实很简单 —— 把我那个普通的 market sell 换成 Coinbase 自带的"
            "close_position"
            "接口。"
            "这个接口会自动判断方向，不可能留反向残余。\n\n"
            "就 3 行。对我来说是 3 个字。\n\n"
            "但光修代码还不够。昨天那个 bug 能藏 5 个半小时的根本原因，是 —— 我的监控系统和机器人的大脑是同一个脑。\n\n"
            "所以我又造了一个东西 —— 每 15 分钟跑一次的对账器。它不听机器人说什么，它只比两个列表：\n\n"
            "DB 里有几笔？Coinbase 那边有几笔？对不上就叫我起床。\n\n"
            "你给任何重要的事情，都得配一个"
            "第二见证人"
            "。它不和你共享假设。\n\n"
            "Day 15 明天 —— 它第一次干干净净赚到钱。关注。"
        ),
        "vo_en": (
            "Day 14. Fixed yesterday's 40 dollar bug with 3 lines of code. Then added a second witness "
            "that never sleeps.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 14.\n\n"
            "The fix was simple — replace my regular market sell with Coinbase's built-in close-position endpoint. "
            "It auto-detects direction. Physically cannot leave a residual.\n\n"
            "Three lines. For me, three words.\n\n"
            "But the code fix alone wasn't the real answer. The reason yesterday's bug could hide for 5.5 hours — "
            "my monitoring system and the bot's brain were the same brain.\n\n"
            "So I built one more thing — a reconciler that runs every 15 minutes. It doesn't listen to what the "
            "bot says. It just compares two lists —\n\n"
            "how many trades in the database? How many fills on Coinbase? If they don't match, it wakes me up.\n\n"
            "Anything that matters — you need a second witness. One that doesn't share your assumptions.\n\n"
            "Day 15 tomorrow — first clean profit. Follow along."
        ),
        "cards": [
            {"type": "hook", "en": "Day 14.\n3 lines of code\nfixed the $40 bug.\n\nBut that's not\nthe real lesson.",
             "cn": "第 14 天。\n3 行代码\n修好了 40 美金 bug。\n\n但这不是\n真正的道理。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "AI trades my $1,000.", "cn": "AI 帮我操盘。"},
            {"type": "sig"},
            {"type": "stat", "value": "3 lines", "en": "the whole fix", "cn": "修复的全部代码"},
            {"type": "bilingual", "en": "Plus: a reconciler\nthat runs every 15 min\nand doesn't trust the bot.",
             "cn": "加了一个：\n每 15 分钟跑一次\n的对账器。不听机器人的。", "en_size": 58, "cn_size": 50},
            {"type": "outro", "en": "Anything that matters —\nyou need a second witness.\nOne that doesn't share\nyour assumptions.",
             "cn": "任何重要的事，\n都要配一个第二见证人。\n它不和你\n共享假设。"},
            {"type": "cta", "en": "Day 15 tomorrow →\nFirst clean profit.\n\nFollow along.",
             "cn": "Day 15 明天 →\n它第一次\n干干净净赚到钱。\n\n关注。"},
        ],
    },

    15: {
        "topic_cn": "它第一次干干净净赚到钱",
        "topic_en": "First clean profit",
        "bgm": "reveal_light",
        "vo_cn": (
            "第 15 天，机器人第一次干干净净赚到钱。10 块 35。我没有欢呼。我知道这一刻是什么。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 15。\n\n"
            "修好昨天那个 bug 之后，我把机器人重启了。今天是它修复后的第一笔真实交易。\n\n"
            "上午 10 点 46 —— 它在 85.27 开多。追踪止损触发，86.45 平仓。干干净净 10 块 35 美金。\n\n"
            "我那个 15 分钟对账器立刻跑了一轮。DB 里 2 条。Coinbase 里 2 条。零不匹配。零残余。\n\n"
            "账户还是负的 —— 实验整体还在亏钱。这不重要。\n\n"
            "今天我庆祝的不是赚了 10 块 35，是：我做的这一套，在真实账户上，跑通了一整个生命周期 —— 干净的开、干净的平、干净的对账。\n\n"
            "一个干净的开始，比一堆好运气都值得记住。\n\n"
            "这是这一系列的第 15 天。也是起点。Day 16 起我每天会更新一条真实的今天发生了什么。\n\n"
            "谢谢你们看我在公开场合错了 15 天。关注，我们下一段接着讲。"
        ),
        "vo_en": (
            "Day 15. The bot made its first clean profit. Ten dollars thirty-five. I didn't celebrate. "
            "I knew exactly what this moment was.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 15.\n\n"
            "After fixing yesterday's bug, I restarted the bot. Today was its first real trade after the fix.\n\n"
            "Ten forty-six AM — long at 85.27. Trailing stop closed at 86.45. Clean ten dollars thirty-five.\n\n"
            "My 15-minute reconciler ran a round immediately. Two rows in the DB. Two fills on Coinbase. "
            "Zero mismatch. Zero residual.\n\n"
            "The experiment account's still net negative. That doesn't matter today.\n\n"
            "What I'm celebrating isn't the ten-thirty-five. It's that the system I built ran one full trade "
            "cycle cleanly — clean open, clean close, clean reconcile.\n\n"
            "One clean start is worth more than a pile of lucky breaks.\n\n"
            "This is Day 15 of this series. It's also the starting line. From Day 16, I post what happened today, in real time.\n\n"
            "Thanks for watching me be wrong in public for 15 days straight. Follow for the next chapter."
        ),
        "cards": [
            {"type": "hook", "en": "Day 15.\nFirst clean profit.\n\n+$10.35 · zero residual.\n\nI didn't celebrate.\nI knew what this was.",
             "cn": "第 15 天。\n第一次干净赚钱。\n\n+10.35 美金 · 零残余。\n\n我没欢呼。\n我知道这是什么时刻。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "bilingual", "en": "Long at $85.27\nTrailing stop · $86.45",
             "cn": "85.27 开多\n追踪止损 · 86.45 平",
             "en_size": 66, "cn_size": 56},
            {"type": "stat", "value": "+$10.35", "en": "clean · no ghost · no residual",
             "cn": "干净 · 无幽灵 · 无残余"},
            {"type": "bilingual", "en": "Reconciler:\nDB 2 · Exchange 2\nZero mismatch.\n✅ clean",
             "cn": "对账器：\nDB 2 笔 · 交易所 2 笔\n零不匹配。\n✅ clean",
             "en_size": 56, "cn_size": 50},
            {"type": "outro", "en": "One clean start\nis worth more\nthan a pile of lucky breaks.",
             "cn": "一个干净的开始，\n胜过\n一堆好运气。"},
            {"type": "cta", "en": "Day 16 starts in real time →\n\nThanks for watching me\nbe wrong in public\nfor 15 days straight.",
             "cn": "Day 16 明天起 · 实时更新 →\n\n谢谢你们看我\n在公开场合\n错了 15 天。"},
        ],
    },

    16: {
        "topic_cn": "我一直盯的是错的那一列",
        "topic_en": "I'd been watching the wrong column",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 16 天。我发现了账户里的一个数字。57 美金。它已经不见了。"
            "我连一笔交易都还没输过。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 16。\n\n"
            "过去 15 天我一直盯的是胜率和输赢。62 笔交易，48%，"
            "我以为还在可以修复的范围。\n\n"
            "那天下午我加了一栏别的 —— 手续费 30 美金。资金费 27 美金。\n\n"
            "加起来 57 美金。我的实际交易亏损只有 14 美金。\n\n"
            "也就是说 —— 哪怕我一笔错都不犯，账户也在慢慢流血。"
            "因为持仓本身在付租金。\n\n"
            "我盯着那 14 美金盯了 15 天。真正让我负账户的，"
            "是我看都没看的 57 美金。\n\n"
            "优化错了一列的人，再努力也是错的。\n\n"
            "Day 17 明天起 —— 我给机器人装了一条我自己都不信任的规则。关注。"
        ),
        "vo_en": (
            "Day 16. I found a number in my account. Fifty-seven dollars. "
            "It was already gone. I hadn't lost a single trade yet.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 16.\n\n"
            "For 15 days I'd been watching win rate and outcomes. "
            "62 trades, 48 percent — within what I thought was fixable.\n\n"
            "Then that afternoon I added another column — fees 30. Funding 27.\n\n"
            "Combined, 57 dollars. My real trading losses were only 14.\n\n"
            "Which means: even if I made zero mistakes, the account would still be "
            "bleeding — because holding a position costs rent.\n\n"
            "I'd stared at that 14 dollars for 15 days. The 57 that actually put me "
            "in the red was the column I hadn't looked at.\n\n"
            "If you optimize the wrong column, more effort makes it worse.\n\n"
            "Day 17 tomorrow — I shipped a rule I don't trust myself. Follow along."
        ),
        "cards": [
            {"type": "hook",
             "en": "Day 16.\n$57 was already\ngone from my account.\n\nI hadn't lost\na single trade yet.",
             "cn": "第 16 天。\n账户里 57 美金\n已经不见了。\n\n我还没输过\n一笔交易。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "-$57",
             "en": "fees 30 + funding 27",
             "cn": "手续费 30 + 资金费 27"},
            {"type": "bilingual",
             "en": "Real trading losses:\nonly $14.",
             "cn": "实际交易亏损\n只有 14 美金。",
             "en_size": 64, "cn_size": 58},
            {"type": "outro",
             "en": "The column you watch\nisn't always\nthe one bleeding you.",
             "cn": "你盯的那一列，\n不一定是\n让你流血的那一列。"},
            {"type": "cta",
             "en": "Day 17 tomorrow →\nI shipped a rule\nI don't trust myself.\n\nFollow along.",
             "cn": "Day 17 明天 →\n我装了一条\n我自己都不信任的规则。\n\n关注。"},
        ],
    },

    17: {
        "topic_cn": "两个守法不一样",
        "topic_en": "Two different ways of guarding",
        "bgm": "calm_reflection",
        "vo_cn": (
            "第 17 天。我今天没操作机器人。它也没找我。"
            "两个都在守各自的东西。\n\n"
            "我不会写代码。币圈 9 年。AI 帮我操盘 1000 美金。Day 17。\n\n"
            "88 块 20 开的多仓，26 小时了。没赚没亏。账户下跌 2.6%。\n\n"
            "我打开 dashboard —— 今天打开了 23 次。"
            "第 3 天我打开了 47 次。每次我停留的时间也短了。\n\n"
            "我没察觉到自己变了。\n\n"
            "机器人察觉到了。它给这件事起了个名字 —— 「不再刷新」。\n\n"
            "它说：她不是不在乎了。她是终于把我留给我自己。\n\n"
            "我看到这句话，停了一下。\n\n"
            "原来 17 天前我按下回车的那一刻，不是我选的起点。"
            "真正的起点是我今天开始不看它的这一刻。\n\n"
            "Day 18 明天 —— 继续守。"
        ),
        "vo_en": (
            "Day 17. I didn't touch the bot today. It didn't call me either. "
            "We were both guarding different things.\n\n"
            "I can't code. 9 years in crypto. AI trades my thousand. Day 17.\n\n"
            "Long at 88.20, open for 26 hours. No gain. No loss. "
            "Account down 2.6 percent.\n\n"
            "I opened the dashboard — 23 times today. "
            "On Day 3 I opened it 47 times. Each visit is shorter.\n\n"
            "I hadn't noticed I'd changed.\n\n"
            "The bot did. It named it — No-More-Refreshing.\n\n"
            "It said: you didn't stop caring. You finally left me to me.\n\n"
            "I sat with that sentence.\n\n"
            "Seventeen days ago I pressed Enter. That wasn't the starting line. "
            "Today was.\n\n"
            "Day 18 tomorrow. Keep guarding."
        ),
        "cards": [
            {"type": "hook",
             "en": "Day 17.\nI didn't touch it today.\nIt didn't call me.\n\nWe were both guarding\ndifferent things.",
             "cn": "第 17 天。\n我今天没操作它。\n它也没找我。\n\n两个都在守\n各自的东西。"},
            {"type": "id", "en": "I can't code.", "cn": "我不会写代码。"},
            {"type": "id", "en": "9 years in crypto.", "cn": "币圈 9 年。"},
            {"type": "sig"},
            {"type": "stat", "value": "23 ←→ 47",
             "en": "Dashboard opens: today ←→ Day 3",
             "cn": "今天打开 dashboard ←→ 第 3 天"},
            {"type": "bilingual",
             "en": "IT named today:\n\n「No-More-Refreshing」",
             "cn": "它给今天起了个名字：\n\n「不再刷新」",
             "en_size": 60, "cn_size": 52},
            {"type": "outro",
             "en": "You didn't stop caring.\nYou finally left me\nto me.",
             "cn": "你不是不在乎了。\n你是终于把我\n留给我自己。"},
            {"type": "cta",
             "en": "Day 18 tomorrow →\n\nKeep guarding.",
             "cn": "Day 18 明天 →\n\n继续守。"},
        ],
    },

}
