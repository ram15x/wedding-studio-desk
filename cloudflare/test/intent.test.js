import test from "node:test";
import assert from "node:assert/strict";
import { directFactQuestion, factAnswer, groundedFactReply, isConversationalGreeting, modelIntent, parseRsvp } from "../src/index.js";

const guest = {
  functions_json: JSON.stringify(["Mehendi", "Sangeet", "Wedding", "Reception"]),
  function_responses_json: "{}",
};

test("count-only RSVP is recorded as coming", () => {
  const parsed = parseRsvp("Hum 6 log aayenge", guest, {});
  assert.equal(parsed.updates.party_size, 6);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
    Mehendi: "coming",
    Sangeet: "coming",
    Wedding: "coming",
    Reception: "coming",
  });
});

test("mixed RSVP updates each function separately", () => {
  const parsed = parseRsvp(
    "Hum 2 log aayenge shaadi mein, reception nahi aa paayenge",
    guest,
    {},
  );
  assert.equal(parsed.updates.party_size, 2);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
    Wedding: "coming",
    Reception: "not_coming",
  });
});

test("a function-specific mixed RSVP leaves unmentioned functions unchanged", () => {
  const parsed = parseRsvp(
    "Hum 2 log aayenge shaadi mein, reception nahi aa paayenge",
    guest,
    {},
  );
  const changed = JSON.parse(parsed.updates.function_responses_json);
  assert.deepEqual(changed, { Wedding: "coming", Reception: "not_coming" });
  assert.equal("Mehendi" in changed, false);
  assert.equal("Sangeet" in changed, false);
});

test("a later travel update does not reverse an explicit function decline", () => {
  const guestAfterMixedReply = {
    ...guest,
    function_responses_json: JSON.stringify({
      Wedding: "coming",
      Reception: "not_coming",
    }),
  };
  const parsed = parseRsvp(
    "21 ko train se aayenge, room chahiye",
    guestAfterMixedReply,
    { wedding_date: "2026-11-21" },
  );
  const changed = JSON.parse(parsed.updates.function_responses_json);
  assert.deepEqual(changed, {
    Mehendi: "coming",
    Sangeet: "coming",
    Wedding: "coming",
    Reception: "not_coming",
  });
  assert.equal(parsed.updates.arrival_date, "2026-11-21");
  assert.equal(parsed.updates.arrival_mode, "train");
  assert.equal(parsed.updates.needs_room, 1);
});

test("natural month-name arrival dates save without an LLM response", () => {
  const facts = { "wedding date": "2026-11-22", "mehendi date": "2026-11-19" };
  for (const message of [
    "We're coming for the wedding, 2 people, flight on 20 Nov 2026. We need a room and pickup.",
    "I arrive on 20 November 2026 by flight and need a pickup.",
  ]) {
    const parsed = parseRsvp(message, guest, facts);
    assert.equal(parsed.updates.arrival_date, "2026-11-20", message);
    assert.equal(parsed.updates.arrival_mode, "flight", message);
    assert.equal(parsed.updates.needs_pickup, 1, message);
  }
});

test("month-name arrival without a year resolves only from a unique wedding date", () => {
  const parsed = parseRsvp("20 Nov ko flight se aa rahe hain", guest, {
    "wedding date": "2026-11-22", "sangeet date": "2026-11-20",
  });
  assert.equal(parsed.updates.arrival_date, "2026-11-20");
});

test("invalid or ambiguous arrival dates are not silently stored", () => {
  const invalid = parseRsvp("Arriving by flight on 31 February 2026", guest, {});
  assert.equal(invalid.updates.arrival_date, undefined);
  assert.ok(invalid.notes.includes("ambiguous_arrival_date"));
  const ambiguous = parseRsvp("Arriving on 20 Nov by train", guest, {
    "wedding date": "2026-11-20", "other date": "2027-11-20",
  });
  assert.equal(ambiguous.updates.arrival_date, undefined);
  assert.ok(ambiguous.notes.includes("ambiguous_arrival_date"));
});

test("a casual Hinglish pickup request is recorded", () => {
  const parsed = parseRsvp(
    "Haan aa rahe hain, 2 log, 20 ko flight se. Room chahiye aur pickup bhi.",
    guest,
    { "sangeet date": "2026-11-20" },
  );
  assert.equal(parsed.updates.needs_pickup, 1);
  assert.equal(parsed.updates.needs_room, 1);
  assert.equal(parsed.updates.arrival_mode, "flight");
  assert.equal(parsed.updates.arrival_date, "2026-11-20");
});

test("natural arrangement wording records room and pickup requests", () => {
  const parsed = parseRsvp(
    "We will come by train on 21 November 2026, please arrange pickup and a room.",
    guest,
    {},
  );
  assert.equal(parsed.updates.arrival_date, "2026-11-21");
  assert.equal(parsed.updates.arrival_mode, "train");
  assert.equal(parsed.updates.needs_pickup, 1);
  assert.equal(parsed.updates.needs_room, 1);
});

test("natural room and pickup declines override earlier positive mentions", () => {
  const parsed = parseRsvp(
    "We need a room and pickup, but we don't need a room or pickup after all.",
    guest,
    {},
  );
  assert.equal(parsed.updates.needs_room, 0);
  assert.equal(parsed.updates.needs_pickup, 0);
});

test("15 realistic guest messages produce grounded RSVP, travel, or fact results", () => {
  const cases = [
    ["Hum 6 log aayenge", {}, { party_size: 6, function_responses_json: { Mehendi: "coming", Sangeet: "coming", Wedding: "coming", Reception: "coming" } }],
    ["Haan aa rahe hain, 4 log, 21 ko train se", { "wedding date": "2026-11-22", "sangeet date": "2026-11-21" }, { party_size: 4, arrival_mode: "train", arrival_date: "2026-11-21" }],
    ["Hum 2 log aayenge shaadi mein, reception nahi aa payenge", {}, { party_size: 2, function_responses_json: { Wedding: "coming", Reception: "not_coming" } }],
    ["Nahi aa payenge, sorry", {}, { function_responses_json: { Mehendi: "not_coming", Sangeet: "not_coming", Wedding: "not_coming", Reception: "not_coming" } }],
    ["Mehendi nahi aa payenge, wedding aa rahe hain", {}, { function_responses_json: { Mehendi: "not_coming", Wedding: "coming" } }],
    ["Reception mein haan aa rahe hain", {}, { function_responses_json: { Reception: "coming" } }],
    ["We are coming for wedding, 3 people", {}, { party_size: 3, function_responses_json: { Wedding: "coming" } }],
    ["Flight on 20 Nov 2026, room chahiye and pickup", {}, { arrival_date: "2026-11-20", arrival_mode: "flight", needs_room: 1, needs_pickup: 1 }],
    ["I arrive on 20 November 2026 by flight and need a pickup", {}, { arrival_date: "2026-11-20", arrival_mode: "flight", needs_pickup: 1 }],
    ["21 ko train se", { "wedding date": "2026-11-22", "sangeet date": "2026-11-21" }, { arrival_date: "2026-11-21", arrival_mode: "train" }],
    ["We'll arrive 20 Nov by flight", { "sangeet date": "2026-11-20" }, { arrival_date: "2026-11-20", arrival_mode: "flight" }],
    ["Room chahiye aur pickup bhi", {}, { needs_room: 1, needs_pickup: 1 }],
    ["Room nahi chahiye, pickup nahi chahiye", {}, { needs_room: 0, needs_pickup: 0 }],
    ["I need a pickup for my train on 19 November", { "wedding date": "2026-11-22", "mehendi date": "2026-11-19" }, { arrival_date: "2026-11-19", arrival_mode: "train", needs_pickup: 1 }],
    ["Coming on 19 Nov 2026 in a train", {}, { arrival_date: "2026-11-19", arrival_mode: "train" }],
  ];
  assert.equal(cases.length, 15);
  for (const [message, facts, expected] of cases) {
    const parsed = parseRsvp(message, guest, facts);
    for (const [key, value] of Object.entries(expected)) {
      const actual = key === "function_responses_json"
        ? JSON.parse(parsed.updates[key] || "{}")
        : parsed.updates[key];
      assert.deepEqual(actual, value, message);
    }
  }
});

test("an explicit Hinglish pickup decline overrides a positive mention", () => {
  const parsed = parseRsvp("Pickup bhi nahi chahiye", guest, {});
  assert.equal(parsed.updates.needs_pickup, 0);
});

test("short greetings with small talk do not get routed as unknown questions", () => {
  assert.equal(isConversationalGreeting("Hi, how are you?"), true);
  assert.equal(isConversationalGreeting("Hey, what can you help me with?"), true);
  assert.equal(isConversationalGreeting("Hi, when is Mehendi?"), false);
});

test("venue facts are phrased as a reply in the guest's language", () => {
  const facts = { venue: "Lotus Hall" };
  assert.equal(factAnswer("Where is the venue?", facts, "english"), "The venue is Lotus Hall.");
  assert.equal(factAnswer("Venue kahan hai?", facts, "hinglish"), "Venue Lotus Hall hai.");
});

test("schedule answer turns stored date and timestamp into a human sentence", () => {
  const facts = { "mehendi time": "2026-11-19 16:00" };
  assert.equal(
    groundedFactReply(["mehendi time"], facts, "english"),
    "Mehendi is 19 November 2026 at 4:00 PM.",
  );
});

test("deterministic schedule fallback formats the date and time as a sentence", () => {
  const facts = {
    "Mehendi Date": "2026-11-19",
    "Mehendi Time": "2026-11-19 16:00",
  };
  assert.equal(
    factAnswer("Mehendi kab hai?", facts, "hinglish"),
    "Mehendi 19 November 2026 at 4:00 PM hai.",
  );
});

test("natural-language intent can update a mixed RSVP without exact phrase rules", () => {
  const parsed = parseRsvp(
    "We would love to join the mehendi and wedding, but have a prior commitment for sangeet. There will be two of us.",
    guest,
    {},
    {
      kind: "rsvp",
      function_responses: {
        Mehendi: "coming",
        Wedding: "coming",
        Sangeet: "not_coming",
      },
      party_size: 2,
    },
  );
  assert.equal(parsed.updates.party_size, 2);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
    Mehendi: "coming",
    Wedding: "coming",
    Sangeet: "not_coming",
  });
});

test("a plan mentioning wedding is not treated as a wedding-fact question", () => {
  for (const message of [
    "We would love to join the mehendi and wedding, but have a prior commitment for sangeet.",
    "We're planning to come for the mehendi and wedding, just 2 of us, but we can't make it to the sangeet.",
  ]) assert.equal(directFactQuestion(message), false, message);
  assert.equal(directFactQuestion("When is the wedding?"), true);
});

test("natural English RSVP with a party count and mixed attendance updates without the model", () => {
  const parsed = parseRsvp(
    "We're planning to come for the mehendi and wedding, just 2 of us, but we can't make it to the sangeet.",
    guest,
    {},
  );
  assert.equal(parsed.updates.party_size, 2);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
    Mehendi: "coming",
    Wedding: "coming",
    Sangeet: "not_coming",
  });
  assert.equal(parsed.notes.includes("rsvp"), true);
});

test("number words and common attendance paraphrases are parsed as RSVP", () => {
  const parsed = parseRsvp(
    "Two of us will be there for the wedding, but we cannot make it to reception.",
    guest,
    {},
  );
  assert.equal(parsed.updates.party_size, 2);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
    Wedding: "coming",
    Reception: "not_coming",
  });
});

test("OpenRouter tries the next configured key after a rate limit and validates its result", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (_url, init) => {
    calls.push(init);
    if (calls.length === 1) return { status: 429, ok: false };
    return {
      status: 200,
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({
          kind: "rsvp",
          function_responses: { Mehendi: "coming", Sangeet: "not_coming", Unknown: "coming" },
          party_size: 2,
          language: "english",
        }) } }],
      }),
    };
  };
  try {
    const result = await modelIntent(
      "We plan to come to mehendi and skip sangeet, two of us.",
      guest,
      {},
      { OPENROUTER_API_KEYS: "test-key-one,test-key-two", OPENROUTER_MODELS: "openrouter/free" },
    );
    assert.equal(calls.length, 2);
    assert.deepEqual(result.function_responses, { Mehendi: "coming", Sangeet: "not_coming" });
    assert.equal(result.party_size, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
