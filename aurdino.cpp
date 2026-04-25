#include <Servo.h>

Servo myServo;
const int redLED = 8;
const int greenLED = 5;

void setup() {
  Serial.begin(9600);
  pinMode(redLED, OUTPUT);
  pinMode(greenLED, OUTPUT);
  myServo.attach(9);
  myServo.write(0); // Start at 0
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd == '1') { 
      digitalWrite(redLED, HIGH); digitalWrite(greenLED, LOW);
      myServo.write(45); 
    } 
    else if (cmd == '2') { 
      digitalWrite(redLED, LOW); digitalWrite(greenLED, HIGH);
      myServo.write(90); 
    }
    else if (cmd == '3') { // NIGHT LIGHT MODE
      digitalWrite(greenLED, HIGH); digitalWrite(redLED, HIGH);
      myServo.write(180);
    }
    else if (cmd == 'P') { // Pinching (Drawing)
      digitalWrite(redLED, HIGH); digitalWrite(greenLED, LOW);
    }
    else if (cmd == '0' || cmd == '4' || cmd == '5' || cmd == 'L') { 
      digitalWrite(redLED, LOW); digitalWrite(greenLED, LOW);
      myServo.write(0); 
    }
  }
}