# CareBack talk track

*Draft, 2026-11-25. Narration for the short presentation and the video, in Don's voice, from his story of 2026-11-25. About 4½ minutes at a speaking pace (about 700 words). Revised 2026-11-26 after the deck's design critique: the product shown on slide 8 and a recruiting ask on the close. Lines in [brackets] are what's on screen. Every figure is sourced at the end; check the notes before changing one.*

---

## 1. The system (0:00)

[Slide 2: 18% of the US economy; the question underneath]

Healthcare is eighteen percent of the American economy. There's a lot of good in that. There's also a lot of confusion, and a lot of bloat.

So let me ask you: do you read your medical bills? In detail? And do you understand them?

## 2. Who pays when it goes wrong (0:25)

[Slide 3: "If you buy your own coverage, more of the bill lands on you." Bars $2,759 → $3,786, +37%]

More and more of the bill is landing on us. If you buy your own coverage on the ACA Marketplace, the average deductible went from about $2,760 in 2025 to about $3,790 in 2026. That's up thirty-seven percent in a single year.

[Slide 4: "People 55 and over account for most US health spending." 57% of spending · 30% of people]

And it lands hardest on people like me. People fifty-five and over are thirty percent of the population, but we account for fifty-seven percent of all health spending.

[Slide 5: "When there's a billing mistake, the bill comes to us."]

So when there's a billing mistake, the bill comes to us. We're the first line of defense. And we don't have the billing experts the insurers have. We're left to fend for ourselves.

## 3. How I found out (1:10)

[Slide 6: "Same treatment. Different bills." Two panels: the treatment, the same every month; what was coded and billed, not the same]

I didn't realize how broken this was until I had a chronic health problem to deal with. Your annual checkup? They probably get that right. Anything more complex, and in my experience the mistakes start to show up.

I was having a monthly series of eye injections for my vision. Same treatment every month. But what was coded, and what I was billed, wasn't the same.

We'd changed insurers at the end of 2025, and at five to six hundred dollars a visit, every month, I knew 2026 was going to hit my deductible hard. So I went back through the earlier charges and projected the rest of the year. The bills weren't consistent. When I drilled in, they really weren't, and I was paying more.

I used AI to find the outliers. Knowing the treatment was the same, I went back to my provider and had the visits reclassified: re-coded to match what was actually done. That saved me hundreds of dollars.

## 4. It's not just me (2:00)

[Slide 7: two cards: the $4,000+ ER visit; billed $315, circled in red pen, against $275 owed per the insurer]

Then I started asking around. A colleague went to the ER and was given a pain reliever. The bill was over four thousand dollars, because it was coded as an ambulance service. When a mistake is that egregious, at least you notice it.

Most aren't. Recently my provider couldn't give me an itemized bill, just a statement saying I owed three hundred fifteen dollars. My insurer rejected the first claim; once it was resubmitted, it confirmed I owed the negotiated rate: two hundred seventy-five. The provider never got the message. They kept asking for $315 by mail, email and phone, when I'd already paid. I had to show them the right amount and ask for a refund.

## 5. Why CareBack (2:45)

That's when I realized I didn't need to fix this for myself. It needs fixing, period.

[Slide 8: the fictional Riverview visit: the bill, the EOB and the HSA payment side by side, the $150 gap circled]

That's why I started CareBack. Here's what it does, on a made-up visit. Your provider says you owe $348. Your insurer's explanation of benefits says you owe $198, and that's what you paid from your HSA. CareBack lines the three up and circles the $150 gap. It doesn't call it an error; it says it's worth a closer look, shows you the documents, and drafts the letter if you want to ask. You decide what's sent.

[Slide 9: "What's built, what's next." Built and running, on the left; where developers and nonprofits come in, on the right]

So what exists today? CareBack is built and running. You can upload or forward your bills, EOBs and HSA exports. It matches every visit line by line and gives each one a status. It removes names and member numbers before any AI reads a document. It drafts the letter, and you decide what's sent. It's Python, FastAPI and Postgres, MIT licensed, and live at carebackhealth.com.

And it's free. No fee, no cut of what you get back.

What's next is where you come in. Developers: the hardest problems are reading documents accurately and matching them to the right visit. Nonprofits: you already serve the households who need this most, and you know what they need.

[Slide 10: "Build it with us." One ask for developers and nonprofits; Don's photo, LinkedIn and carebackhealth.com]

When it comes to your medical bills, we've got your back. But I can't do this alone.

Before we open CareBack to every household, I'm looking for the people who'll help carry it. If you're a developer or you run a nonprofit, and you want to help, talk to me. Find me on LinkedIn, or start at carebackhealth.com.

---

## Source notes

| Line | Figure | Source |
| --- | --- | --- |
| §1 | Health spending was 18.0% of US GDP in 2024 | CMS National Health Expenditure data (historical), via the problem statement |
| §2 | Average deductible in ACA Marketplace plans, weighted by plan selection: $2,759 in 2025, $3,786 in 2026 (+37.2%). Individual deductible, HealthCare.gov states, catastrophic and platinum plans excluded | KFF, "Deductibles in ACA Marketplace Plans, 2014-2026", published Nov 6, 2025, updated May 19, 2026 (https://www.kff.org/affordable-care-act/deductibles-in-aca-marketplace-plans/). Read from the chart on 2026-11-25 |
| §2 | People 55 and over: 57% of total health spending, 30% of the population (2023) | Peterson-KFF Health System Tracker, "How do health expenditures vary across the population?", McGough, Telesford, Cotter and Claxton, March 2, 2026, from the 2023 MEPS (https://www.healthsystemtracker.org/chart-collection/health-expenditures-vary-across-population/) |
| §3, §4 | Don's own visits and a colleague's ER bill | Personal accounts, told as such. No names of providers or the colleague |

### Choices made in the wording (owner to confirm)

1. **"More than 35%" became "thirty-seven percent, on the ACA Marketplace".** KFF's figure is for Marketplace plans, not all coverage. Employer plans rose far less, so saying "the average deductible" without the Marketplace qualifier would overstate it. If the audience is mostly people with employer coverage, drop the figure, or add KFF's employer survey figure once it's sourced.
2. **"A high percentage" of complex bills have mistakes** became "in my experience". We don't yet have a sourced error rate (BACKGROUND §2). Put a figure back once one is sourced.
3. **"Inpatient treatments"** became "a monthly series of eye injections". Eye injections are usually given in an office or outpatient clinic; say "inpatient" only if that's what they were.
4. **"Aspirin with Vicodin"** became "a pain reliever". Vicodin contains acetaminophen, not aspirin, and the drug doesn't matter to the point.
5. **The money-back rule.** Don's own savings are his story and can be told. CareBack itself promises nothing: "helps you get it fixed", never "gets your money back".
6. **Nonprofit.** CareBack is a community service that aims to partner with a leading nonprofit; it doesn't call itself one (owner, 2026-11-25; ABOUT.md, note 1).
