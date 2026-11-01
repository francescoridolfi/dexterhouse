---
name: user-story-writing
description: "How to write user stories with Given/When/Then acceptance criteria that map to requirement ids. Use while drafting user_stories.md."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [meeting_room]
---

# User story writing

Template, one per functional requirement at least:

```
## US-03 Book a seat (covers F-03, F-04)
As a member, I want to book a seat in a course, so that I am sure to attend.
Acceptance:
- Given a course with free seats, when I book, then my booking is confirmed and the free seats decrease by one.
- Given a full course, when I book, then I am added to the waiting list and told my position.
```

Rules:
- One actor and one goal per story; split stories with "and" in the goal.
- Every criterion is observable from outside (an HTTP status, a message, a stored record), never "works correctly".
- Cover the unhappy path: invalid input, missing permission, conflicting action.
- Ids are stable: never reuse a removed id.
- Check both directions: every F-xx is covered by a story and every story covers an F-xx.
