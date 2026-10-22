# YouTube texts

Mode: EXPAND from Juha's notes. The `[fill: ...]` parts are open, nothing about the video is guessed.

## Title (pick one, 100 characters max)

1. Cursed doll only moves when nobody is home (WiFi CSI, ESP32, no camera, no PIR)
2. This doll turns its head when you leave the room. Nobody is watching it. Not even a camera.
3. Nobody Home: a cursed doll that moves when the room is empty

Recommended: 1. It says what it is and has the search words.

## Description

This doll turns its head only when nobody is in the room. When someone comes near, even outside the door, it stops where it is and stays in that pose.

Actually it is an M5Stack AtomS3R (ESP32-S3) and a SG90 micro servo, listening to wifi. The router is the only sensor. The Atom pings the router 100 times a second, every reply brings WiFi CSI (Channel State Information) and moving bodies change it. No PIR, no camera, no extra hardware. The sound of a servo in an empty room is scary enough, so no audio added.

No CGI, no editing tricks, no special effects. It was filmed with my IP surveillance camera, because I can't be in the room to watch it. [fill: where and how long it was filmed, one line]

Made for the element14 Community Halloween Hackathon 2026.

Write-up with the radio analysis, formulas and test results: [fill: element14 project URL]
Code (GPL-2.0): https://github.com/apn201/nobody_home

[fill: chapters. Format, one per line, first must be 0:00:]
0:00 [fill]
0:00 [fill]

Parts: M5Stack AtomS3R, SG90 micro servo, a doll, a 3D printed neck adapter, 5 V USB supply. Wifi router (Google Nest mesh).

#halloween #esp32 #wifi

## Pinned comment (optional)

Everything on the screens in this video is measured data. Nothing is simulated. [fill: or cut]

## Tags (comma separated, 500 characters max, this is 408)

cursed doll, haunted doll, creepy doll, halloween project, halloween 2026, diy halloween, halloween prop, animatronic, esp32, esp32 s3, m5stack, atoms3r, wifi csi, channel state information, wifi sensing, wifi motion detection, through wall sensing, sg90 servo, servo project, arduino, platformio, element14, element14 halloween hackathon, maker project, electronics project, 3d printing, spooky, nobody home

## Video settings

* Thumbnail: `img/thumbnail_doll_v2_1200.jpg` (1280x720 wanted by YouTube, so pad or make a 16:9 crop if you want to avoid the black bars)
* Category: Science & Technology
* Language: English
* Altered content: no (nothing generated, everything real)
* Playlist: [fill]
* Captions: [fill: auto is fine, check "CSI" and "ESP32"]
