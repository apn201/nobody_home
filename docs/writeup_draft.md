# Nobody Home - write-up draft

Mode: EXPAND from Juha's notes, 2026-10-20. Story part only. Finalize when the servo works and the video is shot.

The final post is mostly engineering notes: test results, graphs, schematics. This intro gets trimmed short once the rest is written. Kept long for now.

---

## Short intro (contest page)

This is a doll head that turns only when nobody is in the room. Actually it is an M5Stack AtomS3R and a micro servo, listening to wifi. [fill: one line on what the video shows, once it exists]

## How it started

I'm still in love with exploring what tiny cheap esp32 based controllers can do. I have a Raspberry Pi, but it is in use as a temporary lab server. I have some old Arduinos too, but don't know where. The 3 M5 Atom devices lie on my desk, so it was an easy bet.

A microcontroller alone does not really differ from a PC. And especially for Halloween we need something kinetic.

First idea was how to over-engineer a simple thing. I actually did something like that already: my home automation reads a PIR sensor and triggers a Fingerbot (Zigbee finger robot) to push the button on a camera when something moves. A lot of infrastructure just to push a button on a camera. So that is done.

So we need something kinetic, but "underengineered". Smart, clever, spooky. As Halloween is the theme we do not need to invent the philosopher's stone here. Effect is more important than innovation, but combining existing things in a new way also counts.

So this was my thought process. Thinking about complex things, motion activated props, audio etc. I have an old multimeter I could gut, or the kids' walkie talkies, and the 3D printer to add a lot of Halloween wow around a simple device. Then it hit me. Unknown is scary. It's more scary to realize an object has moved than to actually see it move. Good. Throwing the concept upside down: it only moves when nobody is there to see it. And no need for audio either. The sound of a servo in an empty room is the most scary thing, and it stops when you enter.

Back to the humble ESP controllers. I picked my trusty M5 AtomS3R, which powered my arcade cabinet ([fill: link, see notes]). I do not really need the screen here, but anyway it's good for troubleshooting.

I was thinking about the GPIO, adding PIR sensors etc. Then I remembered the dozens of projects where people "see through walls" using wifi CSI data (Channel State Information, how the signal from the router changes on its way to the receiver). We do not need to see through walls. We just need to know when nobody is near, so we can move the doll head with the servo. More elegant than any external sensor, as wifi is already there. Fairly novel technology and well documented. Sounds like a perfect match. Off we go.

It's a fairly easy concept, but the signal is quite sensitive to all kinds of interference. So I need to run tests, calculate baselines, simulate scenarios. And need to take into account that the video will not be filmed in my lab where I built it. But no need to overthink. We use the info to stop the servo when a person is nearby, so false positives do not matter. Who cares if the servo stops when nobody is there. That simplifies the problem. We just need to make sure it never moves when a person is near. Great.

Just need to order a servo and see what issues it makes. It might draw enough current to reset the esp, or at least disturb the wifi. But we get there later.

And then the same problem as checking the fridge light: how can we know if it moves (or stops) when we can not be in the room? We use my IP surveillance camera. It will make a great demo video. Spooky. And no CGI, editing or special effects. Just a tiny M5 Atom, a micro servo, a never ending ping and some simple signal analysis.

---

## Fill markers

- Intro: what the video shows. Write after the shoot.
- Arcade cabinet link. Hackaday is another contest site; element14 rules on that [fill: check]. The GitHub repo (github.com/apn201/Micro_Arcade) is a neutral alternative.

## Ideas for the later sections (not written yet, facts from NOTES.md)

- How it works, one flat sentence per piece: the Atom pings the router about 100 times a second, every reply brings a CSI frame, 51 subcarriers, a moving variance over 1.5 s, two thresholds from a 60 s empty-room calibration (button 5 s, leave the room).
- What broke, there is plenty: ping timeout of 1 s made 1 s holes in the data (100 ms now), single bad frames that looked like motion (Hampel filter), the empty room drifting to 1.6x its calibration in 1.5 h, 90 weak "someone is here" events in a verified empty hour.
- Video location: the library area, not the lab.
- Backburner, only if time: the "sit perfectly still and it turns toward you" scene. Could be shot in the library, not needed for the entry. Not in the write-up unless it gets done.
- Hallway test: someone moving outside the closed door showed 75x. It freezes before you are in the room.
- Video mode: random creeps, snaps and twitches, freeze mid-move. "A still head in a new pose is creepier than one going back to zero" (Juha, NOTES).
- Pictures: the photo of the Atom scope in red light (22:12 on the clock) works as the lab shot. The PC scope (`scope.py`, waterfall + metric) for a screenshot. Video frames from the IP camera.
- Servo issues once the SG90 arrives: the 1000 uF cap, reset or no reset, does the head's own motion show in CSI.
