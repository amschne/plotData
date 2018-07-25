int analogPin = 0;     // potentiometer wiper (middle terminal) connected to analog pin 2
                       // outside leads to ground and +5V
int val;           // variable to store the value read
unsigned long time;

void setup()
{
  //analogReference(INTERNAL);
  //Serial.begin(9600); // setup serial
  Serial.begin(115200);
}

void loop()
{
  time = micros();
  val = analogRead(analogPin); // read the input pin
  Serial.print(time);
  Serial.print(" ");
  Serial.println(val);
  delay(2);
}
