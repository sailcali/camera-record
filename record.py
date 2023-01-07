#!/home/pi/camera-record/venv/bin/python3

from imutils.video import VideoStream
import argparse
from datetime import datetime
import imutils
import time
import cv2
import os
from collections import UserList
import logging
from discordwebhook import Discord

from dotenv import load_dotenv

DEFAULT_AREA = 800
class RollingAverage:
	def __init__(self):
		self.numbers = []
		self.length = 0
		self.last = 0

	def add(self, number):
		if self.length > 100:
			self.numbers.pop(0)
			self.length -= 1
		self.numbers.append(number)
		self.last = number
		self.length += 1
	
	def average(self):
		if self.length > 10:
			return sum(self.numbers) / self.length
		else:
			return 600
	
	def reset(self):
		self.numbers = []
		self.length = 0


def get_frame(vs, args=None):
	# grab the current frame and initialize the occupied/unoccupied
	# text
	frame = None
	if args:
		frame = vs.read()
		frame = frame if args.get("video", None) is None else frame[1]
	else:
		while frame is None:
			frame = vs.frame
	frame = imutils.resize(frame, width=500)
	return frame

def set_up_reference(frame):
	# resize the frame, convert it to grayscale, and blur it
	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	gray = cv2.GaussianBlur(gray, (21, 21), 0)
	return gray

def get_contours(firstFrame, gray):
	# compute the absolute difference between the current frame and
	# first frame
	frameDelta = cv2.absdiff(firstFrame, gray)
	thresh = cv2.threshold(frameDelta, 25, 255, cv2.THRESH_BINARY)[1]
	# dilate the thresholded image to fill in holes, then find contours
	# on thresholded image
	thresh = cv2.dilate(thresh, None, iterations=2)
	cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,
		cv2.CHAIN_APPROX_SIMPLE)
	return frameDelta, thresh, imutils.grab_contours(cnts)

def determine_occupied(cnts, frame, min_area=DEFAULT_AREA):
	text = "Unoccupied"
	max_contour = 0
	# loop over the contours, add "occupied" if any contours are above the baseline
	for c in cnts:
		cnt_size = cv2.contourArea(c)
		if max_contour < cnt_size:
			max_contour = cnt_size
		# if the contour is too small, ignore it
		if cnt_size < min_area:
			continue
		# compute the bounding box for the contour, draw it on the frame,
		# and update the text
		(x, y, w, h) = cv2.boundingRect(c)
		cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
		text = "Occupied"
	return text, frame, max_contour

def record(stop_time):
	load_dotenv()

	vs = VideoStream(src=0).start()
	time.sleep(2.0)
	
	# initialize the first frame in the video stream
	firstFrame = None
	frame = None
	# i will cycle through 1000000 and reset to 0
	i = 0
	# Only allow 100 frames to be captured before resetting reference frame
	num_continuous = 0
	rolling_avg = RollingAverage()

	# loop over the frames of the stream until the stop time is reached
	while stop_time.hour != datetime.now().hour or stop_time.minute != datetime.now().minute:
		frame = get_frame(vs)
		
		# if the frame could not be grabbed, then we have reached the end
		# of the video
		if frame is None:
			break
		
		gray = set_up_reference(frame)

		# If this is the first frame, or we trigger a number of continuous occupied
		# Reset the reference and continue
		if firstFrame is None or num_continuous > 100 or rolling_avg.average() > 700:
			if rolling_avg.average() > 700:
				logging.debug(f"Rolling average at time {datetime.now()}")
				rolling_avg.reset()
			firstFrame = gray
			num_continuous = 0

			os.chdir("/home/pi/camera-record")
			logging.debug("Reset Reference Frame")
			continue
		
		frameDelta, thresh, cnts = get_contours(firstFrame, gray)
		
		text, frame, max_contour = determine_occupied(cnts, frame)
		
		rolling_avg.add(max_contour)

		if text == "Occupied" and num_continuous == 4:
			# we are now recently occupied. Create a new directory, set it to CWD, and print the name
			new_filename = f"/home/pi/camera-record/recording-" + datetime.strftime(datetime.now(), "%d-%b-%I-%M-%S")
			os.mkdir(new_filename)
			os.chdir(new_filename)
			logging.debug("Occupied! New dir " + new_filename)
			num_continuous += 1

		elif text == "Unoccupied" and num_continuous > 0:
			# Text is unoccupied now, reset things to unoccupied
			logging.debug("Unoccupied")
			num_continuous = 0
			os.chdir("/home/pi/camera-record")

		elif text == "Occupied":
			# We are occupied, but dont need to change directory
			num_continuous += 1
			logging.debug(f"Frame {num_continuous}")

		# draw the text and timestamp on the frame
		cv2.putText(frame, "Room Status: {}".format(text), (10, 20),
			cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
		cv2.putText(frame, datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
			(10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
		# Record the frames
		if text == "Occupied" and num_continuous > 4:
			filename = f"SecurityFeedOccupied{i}.jpg"
			cv2.imwrite(filename, frame)
			if num_continuous == 5:
				discord = Discord(url=os.environ.get("CAMERA_CHANNEL_URL"))
				discord.post(file={"Frame": open(filename, "rb"),})
			
			# Only for debug
			# cv2.imwrite(f"ThreshOccupied{i}.jpg", thresh)
			# cv2.imwrite(f"FrameDeltaOccupied{i}.jpg", frameDelta)
		i += 1
		if i > 1000000:
			i = 0
	# cleanup the camera and close any open windows
	vs.stop()
	vs.stream.release()
	
if __name__ == "__main__":
	# construct the argument parser and parse the arguments
	ap = argparse.ArgumentParser()
	ap.add_argument("-v", "--video", help="path to the video file")
	ap.add_argument("-a", "--min-area", type=int, default=DEFAULT_AREA, help="minimum area size")
	args = vars(ap.parse_args())
	# if the video argument is None, then we are reading from webcam
	if args.get("video", None) is None:
		vs = VideoStream(src=0).start()
		time.sleep(2.0)
	# otherwise, we are reading from a video file
	else:
		vs = cv2.VideoCapture(args["video"])

	# initialize the first frame in the video stream
	firstFrame = None
	# i will cycle through 1000000 and reset to 0
	i = 0
	# Only allow 100 frames to be captured before resetting reference frame
	num_continuous = 0
	rolling_avg = RollingAverage()

	# loop over the frames of the video
	while True:
		if frame == None:
			frame = get_frame(vs, args)
		
		# if the frame could not be grabbed, then we have reached the end
		# of the video
		if frame is None:
			break
		
		gray = set_up_reference(frame)

		# If this is the first frame, or we trigger a number of continuous occupied
		# Reset the reference and continue
		if firstFrame is None or num_continuous > 100 or rolling_avg.average() > 700:
			if rolling_avg.average() > 700:
				print(f"Rolling average at time {datetime.now()}")
				rolling_avg.reset()
			firstFrame = gray
			num_continuous = 0

			os.chdir("/home/pi/camera-record")
			print("Reset Reference Frame")
			continue
		
		frameDelta, thresh, cnts = get_contours(firstFrame, gray)
		
		text, frame, max_contour = determine_occupied(cnts, frame, args["min_area"])
		
		rolling_avg.add(max_contour)

		if text == "Occupied" and num_continuous == 4:
			# we are now recently occupied. Create a new directory, set it to CWD, and print the name
			new_filename = f"/home/pi/camera-record/recording-" + datetime.strftime(datetime.now(), "%d-%b-%I-%M-%S")
			os.mkdir(new_filename)
			os.chdir(new_filename)
			print("Occupied! New dir " + new_filename)
			num_continuous += 1

		elif text == "Unoccupied" and num_continuous > 0:
			# Text is unoccupied now, reset things to unoccupied
			print("Unoccupied")
			num_continuous = 0
			os.chdir("/home/pi/camera-record")

		elif text == "Occupied":
			# We are occupied, but dont need to change directory
			num_continuous += 1
			print(f"Frame {num_continuous}")

		# draw the text and timestamp on the frame
		cv2.putText(frame, "Room Status: {}".format(text), (10, 20),
			cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
		cv2.putText(frame, datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
			(10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
		# Record the frames
		if text == "Occupied" and num_continuous > 4:
			cv2.imwrite(f"SecurityFeedOccupied{i}.jpg", frame)
			# Only for debug
			# cv2.imwrite(f"ThreshOccupied{i}.jpg", thresh)
			# cv2.imwrite(f"FrameDeltaOccupied{i}.jpg", frameDelta)
		i += 1
		if i > 1000000:
			i = 0
	# cleanup the camera and close any open windows
	vs.stop() if args.get("video", None) is None else vs.release()
	cv2.destroyAllWindows()
