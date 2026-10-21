import test from "node:test";
import assert from "node:assert/strict";
import { factAnswer, groundedFactReply, isConversationalGreeting, parseRsvp } from "../src/index.js";

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
