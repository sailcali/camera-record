#!/home/pi/camera-record/venv/bin/python3

from imutils.video import VideoStream
import argparse
from datetime import datetime
import imutils
import time
import cv2
import os

def get_frame(vs, args):
	# grab the current frame and initialize the occupied/unoccupied
	# text
	frame = vs.read()
	frame = frame if args.get("video", None) is None else frame[1]
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

def determine_occupied(cnts, frame, args):
	text = "Unoccupied"
	# loop over the contours, add "occupied" if any contours are above the baseline
	for c in cnts:
		# if the contour is too small, ignore it
		if cv2.contourArea(c) < args["min_area"]:
			continue
		# compute the bounding box for the contour, draw it on the frame,
		# and update the text
		(x, y, w, h) = cv2.boundingRect(c)
		cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
		text = "Occupied"
	return text, frame


# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-v", "--video", help="path to the video file")
ap.add_argument("-a", "--min-area", type=int, default=800, help="minimum area size")
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
# Trigger for when we are in a new directory
newdir = False
# Only allow 100 frames to be captured before resetting reference frame
num_continuous = 0

# loop over the frames of the video
while True:
	
	frame = get_frame(vs, args)
	
	# if the frame could not be grabbed, then we have reached the end
	# of the video
	if frame is None:
		break
	
	gray = set_up_reference(frame)

	# If this is the first frame, or we trigger a number of continuous occupied
	# Reset the reference and continue
	if firstFrame is None or num_continuous > 100:
		firstFrame = gray
		num_continous = 0
		newdir = False
		os.chdir("/home/pi/camera-record")
		print("Reset Reference Frame")
		continue
	
	frameDelta, thresh, cnts = get_contours(firstFrame, gray)
	
	text, frame = determine_occupied(cnts, frame, args)
	
	if not newdir and text == "Occupied":
		# we are now recently occupied. Create a new directory, set it to CWD, and print the name
		new_filename = f"/home/pi/camera-record/recording{i}-" + datetime.strftime(datetime.now(), "%I-%M-%S")
		os.mkdir(new_filename)
		os.chdir(new_filename)
		newdir = True
		print("Occupied! New dir " + new_filename)
	elif text == "Unoccupied" and newdir:
		# Text is unoccupied now, but we are still in the new directory, reset things to unoccupied
		newdir = False
		print("Unoccupied")
		os.chdir("/home/pi/camera-record")
		num_continous = 0
	elif text == "Occupied" and newdir:
		# We are still unoccupied and so still in the new directory
		num_continuous += 1
		print(f"Frame {num_continuous}")

	# draw the text and timestamp on the frame
	cv2.putText(frame, "Room Status: {}".format(text), (10, 20),
		cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
	cv2.putText(frame, datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
		(10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
	# show the frame and record if the user presses a key
	if text == "Occupied":
		cv2.imwrite(f"SecurityFeedOccupied{i}.jpg", frame)
		cv2.imwrite(f"ThreshOccupied{i}.jpg", thresh)
		cv2.imwrite(f"FrameDeltaOccupied{i}.jpg", frameDelta)
	i += 1
	if i > 1000000:
		i = 0

# cleanup the camera and close any open windows
vs.stop() if args.get("video", None) is None else vs.release()
cv2.destroyAllWindows()
