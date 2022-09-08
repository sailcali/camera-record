#!/home/pi/camera-record/venv/bin/python3

from datetime import datetime, date, timedelta
from astral.geocoder import database, lookup
from astral.sun import sun
import pytz
from record import record
from stream import serve
import logging

logging.basicConfig(filename='app.log', format='%(name)s - %(levelname)s - %(message)s')
MINUTES_BEFORE_SUNRISE = 45
HOUR_TO_STOP_SERVER = 22

if __name__ == '__main__':

    while True:
        logging.debug("Serving")
        serve(HOUR_TO_STOP_SERVER)
        logging.debug('Server Shutdown at time ' + datetime.strftime(datetime.now(), '%H-%M-%S'))
        # Get time of sunrise to calculate when to stop recording
        city = lookup("San Diego", database())
        s = sun(city.observer, date=date.today())
        sunrise = s['sunrise']
        sunrise = sunrise.astimezone(tz=pytz.timezone("US/Pacific")) - timedelta(minutes=MINUTES_BEFORE_SUNRISE)
        record(sunrise)
        logging.debug('Recording Stopped at time ' + datetime.strftime(datetime.now(), '%H-%M-%S'))