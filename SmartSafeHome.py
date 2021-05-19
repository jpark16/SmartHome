#Smart + Safe Home source code
#Connects BMP180, DHT11, MQ-2, and MQ-7 to the Raspberry Pi
#Sends captures of the environment in 60 second intervals to AWS DynamoDB

try:
    from gpiozero import Buzzer
    from gpiozero import LED
    from time import sleep
    import time
    import RPi.GPIO as GPIO
    import os
    import sys
    import datetime
    import time
    import boto3
    import Adafruit_DHT
    import bmpsensor
    import RPi.GPIO as GPIO
    import threading
    print("All Modules Loaded ...... ")
except Exception as e:
    print("Error {}".format(e))

# change these as desired - they're the pins connected from the
# SPI port on the ADC to the Cobbler
SPICLK = 11
SPIMISO = 9
SPIMOSI = 10
SPICS = 8
mq7_dpin = 26
mq7_apin = 0
mq2_dpin = 16
mq2_apin = 1

#port init
def init():
         GPIO.setwarnings(False)
         GPIO.cleanup()                 #clean up at the end of your script
         GPIO.setmode(GPIO.BCM)         #to specify whilch pin numbering system
         # set up the SPI interface pins
         GPIO.setup(SPIMOSI, GPIO.OUT)
         GPIO.setup(SPIMISO, GPIO.IN)
         GPIO.setup(SPICLK, GPIO.OUT)
         GPIO.setup(SPICS, GPIO.OUT)
         GPIO.setup(mq7_dpin,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
         GPIO.setup(mq2_dpin,GPIO.IN,pull_up_down=GPIO.PUD_DOWN)
         
#read SPI data from MCP3008(or MCP3204) chip,8 possible adc's (0 thru 7)
def readadc(adcnum, clockpin, mosipin, misopin, cspin):
        if ((adcnum > 7) or (adcnum < 0)):
                return -1
        GPIO.output(cspin, True)

        GPIO.output(clockpin, False)  # start clock low
        GPIO.output(cspin, False)     # bring CS low

        commandout = adcnum
        commandout |= 0x18  # start bit + single-ended bit
        commandout <<= 3    # we only need to send 5 bits here
        for i in range(5):
                if (commandout & 0x80):
                        GPIO.output(mosipin, True)
                else:
                        GPIO.output(mosipin, False)
                commandout <<= 1
                GPIO.output(clockpin, True)
                GPIO.output(clockpin, False)

        adcout = 0
        # read in one empty bit, one null bit and 10 ADC bits
        for i in range(12):
                GPIO.output(clockpin, True)
                GPIO.output(clockpin, False)
                adcout <<= 1
                if (GPIO.input(misopin)):
                        adcout |= 0x1

        GPIO.output(cspin, True)

        adcout >>= 1       # first bit is 'null' so drop it
        return adcout
    
def buzzer(self):
    buzzer = Buzzer(17) #change GPIO pin
    led = LED(27) #chnage GPIO pin
    led.on()
    while True:
        buzzer.on()
        sleep(1)
        buzzer.off()
        sleep(1)
        if GPIO.input(mq7_dpin or mq2_dpin):
            led.off()
            break
    led.off()

#Set up DynamoDB table
class MyDb(object):

    def __init__(self, Table_Name='RpiSmartSafeHomeDB'): #change this to the name of the desired table
        self.Table_Name=Table_Name

        self.db = boto3.resource('dynamodb')
        self.table = self.db.Table(Table_Name)

        self.client = boto3.client('dynamodb')

    @property
    def get(self):
        response = self.table.get_item(
            Key={
                'Sensor_Id':"1"
            }
        )

        return response

    def put(self, Sensor_Id='' , Temperature='', Humidity='', Pressure='', COdensity='', GasAD=''):
        self.table.put_item(
            Item={
                'Sensor_Id':Sensor_Id,
                'Temperature':Temperature,
                'Humidity' :Humidity,
                'Pressure' :Pressure,
                'COdensity':COdensity,
                'GasAD'    :GasAD
            }
        )

    def delete(self,Sensor_Id=''):
        self.table.delete_item(
            Key={
                'Sensor_Id': Sensor_Id
            }
        )

    def describe_table(self):
        response = self.client.describe_table(
            TableName='Sensor'
        )
        return response

    #Setting up the DHT11 sensor
    @staticmethod
    def sensor_value():

        pin = 4
        sensor = Adafruit_DHT.DHT11

        humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)

        if humidity is not None and temperature is not None:
            print('Temp={0:0.1f}*C  Humidity={1:0.1f}%'.format(temperature, humidity))
        else:
            print('Failed to get reading. Try again!')
        return temperature, humidity


def main():
    global counter
    threading.Timer(interval=60, function=main).start() #Change 60 to any amount in seconds for a different delay
    obj = MyDb()
    init()

    #MQ-2 and MQ-7 sensors
    COlevelmq2=readadc(mq2_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
    COlevelmq7=readadc(mq7_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
    COdensity= str("%.2f"%((COlevelmq7/1024.)*100))
    GasAD= str("%.2f"%((COlevelmq2/1024.)*3.3))

    if GPIO.input(mq7_dpin):
           print("CO not leak")
           time.sleep(0.5)
    else:
           print("CO is detected")
           print("Current CO AD vaule = " +str("%.2f"%((COlevelmq7/1024.)*5))+" V")
           print("Current CO density is:" +COdensity+" %")
           count1 = 1
           buzzer(count1)
           time.sleep(0.5)

    if GPIO.input(mq2_dpin):
           print("Gas not leak")
           time.sleep(0.5)
    else:
           print("Gas leakage")
           print("Current Gas AD value = " +GasAD+" V")
           count2 = 2
           buzzer(count2)
           time.sleep(0.5)

    #BMP180 getting readings, but really only wanting pressure
    temp, pressure, altitude = bmpsensor.readBmp180()
    print("Pressure=", pressure)

    #DHT stuff below this point
    Temperature , Humidity = obj.sensor_value()
    
    #Upload to the cloud
    obj.put(Sensor_Id=str(counter), Temperature=str(Temperature), Humidity=str(Humidity),Pressure=str(pressure), COdensity=str(COdensity), GasAD=str(GasAD))
    counter = counter + 1
    print("Uploaded Sample on Cloud T:{},H:{},P:{},COdensity(%):{}, GasAD(V):{} ".format(Temperature, Humidity, pressure, COdensity, GasAD))


if __name__ == "__main__":
    global counter
    counter = 0
    main()
