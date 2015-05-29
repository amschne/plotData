int analogPin = 2;     // potentiometer wiper (middle terminal) connected to analog pin 2
                       // outside leads to ground and +5V
int val;           // variable to store the value read
unsigned long time;

void setup()
{
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
}
