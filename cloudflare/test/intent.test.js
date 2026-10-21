import test from "node:test";
import assert from "node:assert/strict";
import { factAnswer, groundedFactReply, parseRsvp } from "../src/index.js";

const guest = {
  functions_json: JSON.stringify(["Wedding", "Reception"]),
  function_responses_json: "{}",
};

test("count-only RSVP is recorded as coming", () => {
  const parsed = parseRsvp("Hum 6 log aayenge", guest, {});
  assert.equal(parsed.updates.party_size, 6);
  assert.deepEqual(JSON.parse(parsed.updates.function_responses_json), {
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
