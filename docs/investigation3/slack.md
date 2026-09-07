Hello Dr.
following up on your question about what actually makes a test flaky. Here is where I have landed; I would like to check we are aligned before I build anything.

  I think it needs three ingredients together:

  • Hazard — the source of nondeterminism (threads, clock, hash order, leftover state). This is what our token/lexicon approach detects, and it is present in plenty of healthy code too.
  • Reachability — whether that nondeterminism actually flows into what the assertion reads. A test that reads the clock but never asserts on it is not flaky.
  • Control — what breaks that relation: a join instead of a sleep, a sort before comparing, a reset in teardown. This is what FlakeSync and other repair tools add.

  That explains your point exactly. A repair adds a control but does not remove the hazard, so the tokens barely change between the flaky and fixed versions. Our lexicon is really a hazard detector, not a
  flakiness detector.

  So I was thinking- split it into two tiers: hazard detection (roughly what we have with codebert or we can do with a lexicon based approach) and reachability (a dataflow question — backward slice from the assertion, needs resolved types).

  So, the plan I am thinking of- 
  1. Building upon FlakyLens for tier 1, and make it more liberal- not predicting flaky, rather detecting that flaky hazard signals are present.
  2. Building a tier 2, to detect reachability - need proper exploration and analyisis to find the features to work with for this tier.
  3. Combining findings from 2 tier to make the final prediction.
  
  Before building tier 2, I want to test the framing. IDoFT gives ~2,500 flaky tests with the PRs that fixed them, and the pre-fix commit, so I can get the same test before and after. If our current signals
  are near chance at telling those two apart, that confirms the framing with a number. I would pull the test body plus the production methods it actually executes (JaCoCo coverage + Spoon), since some fixes
  are in production code and leave the test untouched.

  Few questions:
  1. Does the hazard / reachability / control split match how you see it?
  2. Is the paired before/after check the right first step, or go straight to reachability?
  3. IDoFT is mostly iteration-order and test-order flakiness, little async or concurrency. Start there anyway, or find concurrency pairs first (FlakeSync, NOD-Test-Repair)?
  4. Should we target particular categories first or work with all?