# HDNxOG — DOORBELL SECURITY


**Team Members**

* Olivier Gingras

* Yacine Ihaddadene
  
## Components (Hardware & Pins)
- **Raspberry Pi** (GPIO + I²C enabled)
- **Ultrasonic sensor (HC-SR04)**
  - TRIG → **BCM 5**
  - ECHO → **BCM 12** (use a safe 3.3 V echo or a voltage divider)
- **Camera**: PiCamera2 (Picamera2)
- **I²C LCD 16×2** (PCF8574 @ 0x27 or 0x3F) — SDA/SCL on bus 1
- **Buzzer (active)** → **BCM 18** (with series resistor)
- **Alert LED (red)** → **BCM 21** (with series resistor)
- **Extra LEDs**: Yellow **BCM 16**, Red **BCM 23**, Green **BCM 24**
- **Fan / Relay module**
  - Fan control → **BCM 22**
  - Relay IN (active-low) → **BCM 17**
  - Use proper transistor/relay module with flyback diode for loads

## Adafruit IO dashboard screenshot( Using CLI for User Interaction )

<img width="1907" height="923" alt="Screenshot 2025-11-30 102603" src="https://github.com/user-attachments/assets/547c90ff-be09-459f-8ec8-136502fec2a4" />

## Flask App (Using Render and Neon DB)

Home Page: 

<img width="1919" height="926" alt="image" src="https://github.com/user-attachments/assets/a41876d7-ddea-490c-a39c-0731c3b976a8" />

Environmental Page:

<img width="1915" height="930" alt="image" src="https://github.com/user-attachments/assets/24ab705f-010e-4c44-a6c7-a613fefa44c7" />

Security Page:

<img width="1913" height="925" alt="image" src="https://github.com/user-attachments/assets/fa4369a3-e6d5-4f02-b7a4-423c5ca762dd" />

Control Page:

<img width="1911" height="825" alt="image" src="https://github.com/user-attachments/assets/ebf495a3-6122-42ac-a61e-b3e34d7e2d2b" />



## Public cloud folder link with daily uploads

[Google Drive with Environment and Security Data](https://drive.google.com/drive/folders/1WrucwgLW0M628I1tBLCbrdHpttixRFfV?usp=sharing)

## **Short Reflection**

In this milestone, we reached our main goal, which was to add at least 3 devices and 3 sensors and to put the whole project into a more organized box. We also decided to add an LCD screen, which makes the system easier to understand for humans and just nicer to use.

We improved the detection part too, instead of using a motion sensor, we switched to an ultrasonic sensor, and that was cool because we linked it with the buzzer, the LCD, an LED, and the camera to make a full alert system.

Some things were harder though. The breadboard wiring was a bit annoying because there were a lot of cables and it got tight, so moving things around wasn’t super fun. Also, the relay was new for us, so understanding exactly how to wire it and how it works took some time.

The only negative point we still have right now is that we weren’t able to reduce the motor speed the way we wanted.

## Final Project CheckPoint

Looking back at the whole project, We are really proud of how much we were able to integrate and how cohesive the system feels now. The biggest win was definitely moving from just a pile of components to a working, integrated security system managed through a clean web dashboard. We learned a ton about both hardware interfacing and web service integration.

## Photos of the Project

<p align="center">
  <img src="https://github.com/user-attachments/assets/37421cf4-1b49-4fdd-a1e5-8d1907b74ed6" alt="Project photo 1" width="360" />
  <img src="https://github.com/user-attachments/assets/67b9724c-76a7-4627-accb-14588d0711be" alt="Project photo 2" width="360" />
</p>


## **Youtube Video**

https://youtu.be/OrRSMOfVJPg





