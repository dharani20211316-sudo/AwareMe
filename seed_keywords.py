"""
Seed script: Push all cognitive distortion regex patterns to MongoDB historyDB.keywords.
Run once to populate, then model_processor.py reads from there.

Usage:
    python seed_keywords.py
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

EXPANDED_PATTERNS = {
    "All-or-Nothing Thinking": [
        r"\b(complete(?:ly)?\s+(?:failure|disaster|waste|useless))",
        r"\b(either\s+.{3,30}\s+or\s+(?:not|nothing|never))\b",
        r"\b((?:totally|completely|absolutely)\s+(?:ruined|worthless|hopeless|useless|awful))",
        r"\b(100%|zero\s+(?:chance|hope))\b",
        r"\b((?:the\s+)?(?:whole|entire)\s+(?:day|week|life|thing|career|year)\s+is\s+(?:ruined|wasted|over|destroyed))",
        r"\b(i\s+(?:am|'m)\s+(?:completely|totally|absolutely)\s+(?:useless|worthless|hopeless|stupid))",
        r"\b((?:don'?t|doesn'?t|never)\s+belong)",
        r"\b((?:won'?t|can'?t)\s+(?:be\s+able\s+to\s+)?(?:do\s+anything|focus\s+on\s+anything|get\s+anything))",
        r"\b((?:you|he|she|they)\s+(?:are?|is)\s+(?:the\s+)?(?:villain|crazy|insane|mental|delusional|toxic|abusive|cheating|stealing|controlling|manipulating|immature|unstable))",
        r"\b((?:you're|he's|she's|they're)\s+(?:(?:the\s+)?(?:villain|crazy|insane|mental|delusional|toxic|abusive|cheating|stealing|controlling|manipulating|immature|unstable)))",
        r"\b((?:you|he|she|they)\s+(?:are?|is)\s+a\s+(?:crazy\s+person|brat|child|liar|loser|snob|jerk|psycho|narcissist|horrible\s+person|bad\s+friend|bad\s+person))",
        r"\b((?:you're|he's|she's|they're)\s+a\s+(?:crazy\s+person|brat|child|liar|loser|snob|jerk|psycho|narcissist|horrible\s+person|bad\s+friend|bad\s+person))",
        r"\b((?:this|that)\s+(?:kid|person|man|woman|guy|girl)\s+(?:is|was)\s+(?:a\s+)?(?:brat|crazy|insane|psycho|villain|jerk|wild|hysterical|dramatic|ridiculous))",
        r"\b((?:he|she|they|you|\w+)\s+(?:is|are|was|were)\s+(?:so\s+)?(?:wild|hysterical|dramatic|ridiculous|unhinged|out\s+of\s+control|out\s+of\s+line))",
        r"\b((?:that|it|this)\s+(?:\w+\s+)?(?:was|were)\s+(?:so\s+)?(?:crazy|insane|wild|mental|nuts|ridiculous|absurd|unreal|stressful))\b",
        r"\b((?:tonight|today|yesterday|last\s+night)\s+was\s+(?:so\s+)?(?:crazy|insane|wild|stressful|hectic|chaotic|intense))\b",
        r"\b((?:i\s+)?(?:started|was|were|got|getting)\s+(?:so\s+|really\s+)?(?:hysterical|dramatic|crazy|unhinged|out\s+of\s+control|aggressive|violent|physical))\b",
        r"\b((?:show\s+up|eat|be\s+there|do\s+it).{0,30}or\s+don'?t\s+(?:come|bother|show\s+up)(?:\s+at\s+all)?)",
        r"\b(you\s+either\s+.{3,40}\s+or\s+.{3,30})",
        r"\b((?:he|she|they|you)\s+(?:has|have)\s+no\s+(?:respect|manners|class|empathy|boundaries|shame|trust|decency))",
        r"\b((?:this|that)\s+is\s+(?:not\s+)?(?:rational|normal|acceptable|sane)\s+(?:behavio(?:u?r)|thinking))",
        r"\b((?:that\s+person|this\s+person|he|she|they|you)\s+need(?:s)?\s+(?:a\s+)?(?:therapist|therapy|help|professional\s+help))",
        r"\b((?:they|he|she)\s+(?:like|love)(?:s)?\s+to\s+be\s+in\s+(?:that\s+)?(?:victim\s+mentality|victim\s+mode))",
        r"\b((?:no,?|naughty|bad|horrible|terrible|awful)\s+(?:girl|boy|person|kid|man|woman))\b",
        r"\b((?:you're|he's|she's|they're)\s+(?:stealing|lying|cheating|manipulating|gaslighting|controlling|abusing))",
        r"\b((?:he|she|they)\s+doesn'?t\s+(?:love|like|care\s+about|respect|want)\s+you)",
        r"\b((?:he|she)\s+doesn'?t\s+(?:love|like|care\s+about|respect|want)\s+(?:her|him))",
        r"\b(if\s+(?:he|she|they)\s+(?:loved|liked|cared|wanted|respected)\s+you,?\s+(?:he|she|they)\s+would(?:\s+\w+){0,6})",
        r"\b(you\s+(?:have|need)\s+to\s+(?:forgive|forget|move\s+on|let\s+(?:it|go|him|her)\s+go|get\s+over|accept|leave|stay|stop|grow\s+up)(?:\s+\w+){0,4})",
    ],
    "Overgeneralization": [
        r"\b(i\s+(?:always|never)\s+(?:fail|mess|screw|ruin|lose|forget|get))",
        r"\b((?:no\s*one|nobody)\s+(?:ever\s+)?(?:loves?|likes?|cares?|listens?|wants?))",
        r"\b((?:everyone|everybody)\s+(?:hates?|leaves?|thinks?\s+i'm?|judges?|is\s+(?:smarter|better|faster|more)))",
        r"\b((?:nothing)\s+(?:ever|good)\s+(?:works?|happens?|goes?))",
        r"\b(i\s+(?:always|never)\s+(?:end\s+up|wind\s+up|make|do\s+(?:things?|it)))",
        r"\b(nobody\s+(?:ever\s+)?(?:will|would|wants?\s+to))",
        r"\b(all\s+(?:men|women|guys|girls|people|kids|friends)\s+(?:\w+\s+){0,3}(?:have|are|do|want|need|think|say|get|lie|cheat))",
        r"\b((?:this|that|it)\s+happens\s+to\s+(?:everyone|everybody|all\s+of\s+us))",
        r"\b(you'?re?\s+never\s+going\s+to\s+(?:\w+\s*){1,5})",
        r"\b(people\s+always\s+(?:\w+\s*){1,6})",
        r"\b((?:he|she|they|you)\s+always\s+(?:\w+\s*){1,4}(?:do(?:es)?|make|get|say|lie|cheat|flake|cancel|bail|come\s+late|show\s+up\s+late))",
        r"\b((?:he|she|they|you)\s+never\s+(?:\w+\s*){0,3}(?:listen|care|ask|help|show|change|learn|respect)(?:s|ed)?)",
        r"\b((?:everyone|everybody)\s+(?:always|never|does|knows|thinks|says|wants|hates|loves)(?:\s+\w+){0,4})",
        r"\b((?:nobody|no\s+one)\s+(?:ever\s+)?(?:cares?|listens?|asks?|helps?|understands?|wants?|gets?\s+it))",
        r"\b(who\s+(?:the\s+\w*\s+)?cares?\b)",
        r"\b((?:she|he|they)\s+(?:is|are)\s+always\s+(?:late|lying|flaking|canceling|complaining|negative|dramatic|rude))",
        r"\b(there'?s?\s+nothing\s+in\s+(?:these|those|the)\s+\w+)",
        r"\b((?:men|women|people|friends|boys|girls|guys|they)\s+come,?\s+(?:and\s+)?(?:they\s+)?go)",
        r"\b(we\s+all\s+(?:make|have|do|want|need|know|feel|say|go\s+through|are|get)\s+(?:\w+\s*){1,5})",
        r"\b(every\s+single\s+(?:thing|time|day|person|one)\s+(?:\w+\s*){1,6})",
        r"\b(not\s+everyone\s+(?:wants?|has|can|will|is\s+going)\s+(?:to\s+)?(?:\w+\s*){1,6})",
        r"\b(another\s+(?:sleepless|bad|terrible|awful|horrible)\s+(?:night|day|week|morning|evening))",
        r"\b(another\s+(?:sister\s+)?(?:fight|argument|drama|disaster|breakup|crisis|meltdown|blowup))",
        r"\b((?:been|was|is)\s+(?:in\s+a\s+)?(?:bad|terrible|awful|foul|nasty|angry|sad|depressed|moody|grumpy|bitchy|salty|badass)(?:\s+(?:ass\s+)?(?:mood|state|place))?\s+all\s+(?:day|night|week|morning|trip|time))",
        r"\b((?:\w+'?s?)\s+been\s+in\s+a\s+(?:bad|terrible|awful|foul|nasty|badass)(?:\s+(?:ass\s+)?mood)?\s+all\s+(?:day|night|week|morning|trip|time))",
        r"\b((?:we'?re?|they'?re?)\s+(?:ending|starting|going\s+through)\s+(?:this|the)\s+(?:\w+\s*){0,4}(?:with\s+)?another(?:\s+\w+){0,4})",
    ],
    "Mental Filtering": [
        r"\b(only\s+(?:bad|negative|wrong|terrible)\s+things?)\b",
        r"\b(nothing\s+(?:good|right|positive)\s+(?:ever\s+)?(?:happens?))",
        r"\b(can'?t\s+see\s+any(?:thing)?\s+(?:good|positive))",
        r"\b(only\s+(?:think|focus|see|remember)\s+(?:about\s+)?(?:the\s+)?(?:bad|negative|wrong))",
    ],
    "Disqualifying the Positive": [
        r"\b((?:just|only)\s+(?:luck|being\s+nice|saying\s+that|pity))\b",
        r"\b(doesn'?t\s+(?:really\s+)?(?:count|matter|mean\s+anything))",
        r"\b((?:anyone|anybody)\s+could\s+(?:have\s+)?(?:done?|do)\s+that)",
        r"\b(they\s+(?:were|are)\s+just\s+(?:being\s+)?(?:nice|polite|kind))",
        r"\b(she\s+(?:doesn'?t|won'?t)\s+know\s+(?:she\s+)?(?:technically|actually)\s+paid)",
        r"\b(but\s+(?:you'?re?|she'?s?|he'?s?)\s+not\s+(?:really\s+)?(?:telling|saying|admitting))",
    ],
    "Jumping to Conclusions": [
        r"\b((?:they|she|he)\s+(?:must|probably)\s+(?:think|hate|be\s+(?:angry|mad|upset)))",
        r"\b(i\s+(?:just\s+)?know\s+(?:it|this|they|i)\s+will\s+(?:fail|go\s+wrong))",
        r"\b((?:this|it)\s+(?:will|is\s+going\s+to)\s+(?:be\s+)?(?:a\s+)?(?:disaster|terrible|awful))",
        r"\b((?:maybe|probably|must\s+be)\s+(?:ignoring|avoiding|hating|angry\s+at|mad\s+at)\s+me)",
        r"\b((?:she|he|they)\s+(?:is|are)\s+(?:ignoring|avoiding|annoyed\s+with|upset\s+with)\s+me)",
        r"\b((?:doesn'?t|don'?t)\s+want\s+to\s+(?:talk|be|hang)\s+(?:to|with)\s+me)",
        r"\b((?:he|she|they|\w+)'?(?:s|re)?\s+(?:just\s+)?trying\s+to\s+(?:make|manipulate|control|gaslight|guilt|trick|use|justify|break|ruin|sabotage|destroy|push|pull|split|separate|turn)(?:\s+\w+){0,5})",
        r"\b(i\s+(?:just\s+)?know\s+(?:he|she|they|\w+)\s+(?:wants?|thinks?|feels?|means?|would|will|hates?)(?:\s+\w+){0,6})",
        r"\b(i\s+(?:just\s+)?know\s+(?:he|she|they|\w+)\s+is\s+(?:going\s+to|trying|lying|hiding|cheating|faking|pretending|avoiding)(?:\s+\w+){0,5})",
        r"\b(i'?m\s+(?:sure|certain|positive|convinced)\s+(?:he|she|they|\w+)\s+(?:is|are|was|were|will|would)(?:\s+\w+){0,6})",
        r"\b((?:he|she|they|\w+)\s+is\s+going\s+to\s+(?:downplay|deny|lie|pretend|blame|twist|make\s+it\s+seem|act\s+like|play\s+the\s+victim)(?:\s+\w+){0,5})",
        r"\b(i\s+already\s+know\s+(?:\w+\s*){1,6}(?:is|are)\s+going\s+to(?:\s+\w+){0,5})",
        r"\b((?:he|she|they|that\s+person)\s+(?:is|are)\s+(?:just\s+)?(?:taking\s+advantage|using\s+(?:you|her|him)|manipulating|gaslighting))",
        r"\b((?:he|she|they)'?(?:s|re)?\s+(?:definitely\s+|clearly\s+|obviously\s+)?cheating\b)",
        r"\b((?:he|she|they)\s+(?:must|probably)\s+(?:think|feel|believe|know|want|be\s+(?:angry|mad|upset|jealous|using|hiding))(?:\s+\w+){0,4})",
        r"\b(looked\s+at\s+(?:me|her|him|us|them)\s+like\s+(?:\w+\s*){2,8})",
        r"\b(you\s+(?:need|have)\s+to\s+(?:break\s+up|leave|run|get\s+out|dump|divorce)(?:\s+\w+){0,5})",
        r"\b(don'?t\s+let\s+(?:him|her|them)\s+(?:manipulate|gaslight|control|use|take\s+advantage)(?:\s+\w+){0,4})",
        r"\b((?:your|her|his|their)\s+(?:mom|dad|friend|boyfriend|girlfriend|husband|wife|partner)\s+is\s+(?:having|going\s+through)\s+(?:a\s+)?(?:midlife\s+crisis|breakdown|manic\s+episode|mental\s+break))",
        r"\b((?:he|she|they)'?(?:s|re)?\s+(?:using|playing)\s+(?:you|her|him|your\s+\w+)(?:\s+\w+){0,4})",
        r"\b((?:sounds?|seems?)\s+(?:like\s+)?(?:a\s+)?(?:very\s+)?(?:controlling|possessive|manipulative|toxic|abusive|unhealthy|codependent|one[- ]?way)(?:\s+\w+){0,3})",
        r"\b((?:he|she|they)\s+(?:says?|said|does|did)\s+(?:that|it|this|\w+)\s+because\s+(?:he|she|they)'?(?:s|re)?\s+(?:\w+\s*){0,3}(?:embarrassed|humiliated|jealous|insecure|afraid|scared|guilty|ashamed|uncomfortable|awkward|nice|polite))",
        r"\b(you\s+only\s+(?:\w+\s*){1,5}because\s+you'?re?\s+(?:embarrassed|humiliated|jealous|afraid|scared|ashamed|insecure|guilty))",
        r"\b(you\s+(?:will|would|are\s+going\s+to)\s+(?:really\s+)?(?:regret|lose|miss|suffer|fail|never)(?:\s+\w+){0,6})",
        r"\b((?:what'?s?|what\s+is)\s+meant\s+for\s+you\s+will\s+(?:always\s+)?find\s+you)",
        r"\b(if\s+(?:he|she|they)\s+(?:loved|cared|wanted|liked)\s+you,?\s+(?:he|she|they)\s+would\s+(?:have\s+)?(?:\w+\s*){1,6})",
        r"\b((?:he|she|they)\s+(?:was|were|is|are)\s+(?:just\s+)?(?:being\s+)?(?:nice|polite)\s+(?:and\s+)?(?:saying\s+that|by\s+saying))",
        r"\b((?:he|she|they)\s+(?:was|were|is|are)\s+(?:just\s+)?(?:embarrassed|humiliated|jealous|insecure|uncomfortable|guilty|ashamed))",
        r"\b((?:he|she|they)\s+didn'?t\s+(?:even\s+)?(?:mind|bother|care|check|think|notice)(?:\s+\w+){0,5})",
    ],
    "Catastrophizing": [
        r"\b((?:my|the)\s+(?:whole\s+)?(?:life|career|future|world)\s+is\s+(?:over|ruined|destroyed))",
        r"\b((?:can'?t|won'?t)\s+(?:ever\s+)?(?:recover|survive|get\s+through))",
        r"\b((?:i\s+)?(?:might|will)\s+(?:never|not)\s+(?:get|find|have|make\s+it|succeed))",
        r"\b((?:chose|choosing)\s+the\s+wrong\s+(?:field|path|career|major|job))",
        r"\b((?:that|it|this)\s+(?:is|was|were)\s+(?:so\s+)?(?:insane|crazy|mental|abuse|sick|ridiculous|absurd|delusional|psychotic|unhinged|nuts|bonkers|horrifi\w*|terrif\w*|stressful))\b",
        r"\b((?:that|it|this)\s+(?:\w+\s+)?(?:is|was|were)\s+(?:so\s+)?(?:insane|crazy|mental|abuse|sick|ridiculous|absurd|delusional|psychotic|unhinged|nuts|bonkers|horrifi\w*|terrif\w*|stressful))\b",
        r"\b((?:that|it|this)\s+(?:was|is)\s+(?:so\s+)?(?:crazy|wild|insane|mental|nuts|stressful|hectic|chaotic|intense))\b",
        r"\b(the\s+damage\s+(?:was|is|has\s+been)\s+done)",
        r"\b((?:going\s+to|will|gonna)\s+lose\s+all\s+(?:trust|hope|faith|respect|credibilit\w*)(?:\s+\w+){0,4})",
        r"\b((?:anyone|anybody)\s+(?:who|that)\s+(?:\w+\s+){1,8}is\s+(?:actually\s+)?(?:mentally\s+unstable|insane|crazy|abusi\w*|psycho\w*))",
        r"\b(\d+\s+(?:to\s+\d+\s+)?(?:weeks?|months?|days?|hours?)\s+is\s+(?:abuse|insane|crazy|mental|torture))",
        r"\b((?:this|that)\s+is\s+(?:not\s+)?(?:rational|normal|sane|healthy|okay)\s+(?:behavio\w*|thinking)?)\b",
        r"\b(what\s+(?:the\s+\w*\s+)?is\s+wrong\s+with\s+(?:you|him|her|them|these\s+people))",
        r"\b((?:this|that)\s+is\s+(?:so\s+)?(?:up|messed\s+up|screwed\s+up|insane|unreal))\b",
        r"\b((?:it'?s?|this|that|(?:he|she|they)'?(?:s|re)?)\s+(?:is\s+)?ruining\s+my\s+(?:life|career|relationship|health|marriage|friendship))",
        r"\b(you\s+never\s+(?:get\s+over|forget|recover\s+from|move\s+on\s+from)(?:\s+(?:losing|it|that|this|a|the)(?:\s+\w+){0,5})?)",
        r"\b((?:this|that)\s+is\s+my\s+(?:biggest|worst|greatest)\s+(?:fear|nightmare|regret))",
        r"\b(you'?ve?\s+(?:already\s+)?(?:lost|ruined|destroyed|wasted)\s+(?:your|the|a)\s+(?:\w+\s*){1,4})",
        r"\b(you\s+(?:will|would|are\s+going\s+to)\s+(?:really\s+)?regret(?:\s+\w+){0,6})",
        r"\b((?:it|this|that)\s+(?:really\s+)?(?:breaks|broke|is\s+breaking)\s+my\s+heart)",
        r"\b((?:it|this|that)\s+(?:just\s+|really\s+)?(?:destroys|destroyed|kills|killed)\s+me)",
        r"\b((?:it|this|that|everything)\s+(?:is\s+)?(?:spiral(?:ing|ed)?\s+out\s+of\s+control))",
        r"\b(chips?\s+away\s+at\s+my\s+(?:soul|heart|sanity|wellbeing|mental\s+health))",
        r"\b((?:it|this|that)\s+(?:really\s+)?sucks)",
        r"\b(another\s+sleepless\s+night)",
        r"\b((?:see|saw|watch(?:ing)?)\s+(?:everything|things?|it\s+all)\s+(?:spiral|fall\s+apart|collapse|crumble|go\s+(?:wrong|south|downhill)))",
    ],
    "Emotional Reasoning": [
        r"\b(i\s+feel\s+(?:like\s+)?(?:a\s+)?(?:failure|burden|worthless|stupid|ugly|loser|fraud))",
        r"\b(i\s+feel\s+(?:so\s+)?(?:dumb|hopeless|helpless|pathetic))",
        r"\b((?:feel(?:s)?)\s+(?:like\s+)?(?:everything|nothing|no\s*one))",
        r"\b(i\s+(?:am|'m)\s+(?:so\s+)?(?:stupid|dumb|useless|worthless|pathetic|a\s+failure))",
        r"\b(i\s+feel\s+like\s+i\s+(?:am|'m|don'?t|can'?t|shouldn'?t))",
        r"\b(i\s+(?:don'?t\s+really\s+)?feel\s+like\s+(?:this|that|the)\s+(?:fight|situation|relationship|conversation|trip|argument|problem|issue|thing)\s+(?:is|was|isn'?t|wasn'?t)(?:\s+\w+){0,6})",
        r"\b(i\s+feel\s+(?:so\s+|pretty\s+|really\s+|very\s+|super\s+)?(?:disrespected|offended|hurt|betrayed|abandoned|ignored|dismissed|invalidated|attacked|targeted|used|manipulated|unsafe|unwelcome|unwanted|uncomfortable|overwhelmed|ambushed))",
        r"\b(i\s+(?:just\s+)?feel\s+(?:so\s+|really\s+)?(?:bad|terrible|awful|sorry|sad|guilty|responsible)\s+for\s+(?:my\s+)?(?:\w+))",
        r"\b(i'?m\s+(?:pretty|so|really|very|just)?\s*(?:offended|hurt|upset|angry|mad|frustrated|disappointed|devastated|heartbroken|disgusted|horrified|shocked|scared|terrified)(?:\s+(?:and|by|about|that)(?:\s+\w+){0,6})?)",
        r"\b((?:this|that|it)\s+is\s+(?:giving\s+me|triggering)(?:\s+\w+){0,5})",
        r"\b((?:this|that)\s+is\s+giving\s+me\s+(?:so\s+much\s+)?(?:PTSD|anxiety|depression|flashback\w*|panic))",
        r"\b(i\s+fe(?:el|lt)\s+(?:so\s+)?(?:bad|weird|grossed\s+out|shocked|disgusted|uncomfortable|icky)(?:\s+\w+){0,10}(?:second[- ]?guess|rethink|doubt|question|can'?t\s+stop))",
        r"\b(i'?m?\s+concerned\s+about\s+(?:these|those|this|that)\s+(?:people|person)\w*)",
        r"\b((?:this|that)\s+is\s+giving\s+me\s+(?:so\s+much\s+)?PTSD)",
        r"\b((?:this|that)\s+is\s+(?:so\s+)?triggering(?:\s+me)?(?:\s+\w+){0,3})",
        r"\b((?:this|that)\s+is\s+(?:insulting|offensive|disrespectful)(?:\s+and\s+(?:that|it)\s+would\s+cut)?)",
        r"\b(i\s+feel\s+like\s+i\s+(?:won'?t|can'?t|will\s+never)\s+(?:find|get|have|be|make|do)(?:\s+\w+){0,6})",
        r"\b(i\s+feel\s+(?:so\s+)?(?:replaced|behind|rejected|robbed|broken|trapped|stuck|lost|invisible|unwanted|unlovable|alone|lonely)\b)",
        r"\b(i\s+feel\s+(?:like\s+)?(?:people|everyone|they|friends?)\s+(?:are\s+)?(?:always\s+)?(?:judging|watching|looking\s+at|staring\s+at|talking\s+about)(?:\s+me)?)",
        r"\b(i\s+(?:feel|felt)\s+(?:like\s+)?(?:i\s+)?(?:was|am|'m)\s+(?:really\s+)?(?:going\s+crazy|losing\s+(?:my\s+mind|it)|the\s+problem|not\s+enough|too\s+much|broken))",
    ],
}


def seed():
    mc = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mc["historyDB"]
    col = db["keywords"]

    # Upsert the full pattern set
    result = col.update_one(
        {"_id": "expanded_patterns_v2"},
        {"$set": {"patterns": EXPANDED_PATTERNS, "updated_at": datetime.now()}},
        upsert=True,
    )

    total = sum(len(v) for v in EXPANDED_PATTERNS.values())
    categories = len(EXPANDED_PATTERNS)

    if result.upserted_id:
        print(f"Inserted new document: {categories} categories, {total} patterns")
    else:
        print(f"Updated existing document: {categories} categories, {total} patterns")

    # Verify
    doc = col.find_one({"_id": "expanded_patterns_v2"})
    stored = sum(len(v) for v in doc["patterns"].values())
    print(f"Verified in MongoDB: {len(doc['patterns'])} categories, {stored} patterns")
    mc.close()


if __name__ == "__main__":
    seed()
