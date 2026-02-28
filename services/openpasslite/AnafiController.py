import os
import olympe
import gc
import subprocess
import time
from AnafiCamera import AnafiCamera
from AnafiPiloting import AnafiPiloting
from AnafiRTH import AnafiRTH
from olympe.messages.ardrone3.PilotingState import PositionChanged, AttitudeChanged
from olympe.messages.obstacle_avoidance import set_mode, status

class AnafiController:
	''' 
	Parrot Olympe wrapper for controlling Parrot Anafi drones.
	
	...
	
	Attributes
	----------
	drone_ip : str
		the drone's ip address
	drone_rtsp_port : str
		the drone's rtsp port which connects to the live stream
	drone_url : str
		the url used request to make requests from the drone
	drone : olympe.Drone
		the drone object
	camera : AnafiCamera
		the drone camera method interface
	piloting : AnafiPiloting
		the drone flight controls method interface
	rth : AnafiRTH
		the drone Return From Home (RTH) methods interface	

	Methods
	-------
	connect()
		Establishes a connection with the drone
	disconnect()
		Breaks current connection with the drone
	get_drone_coordinates()
		Returns drone's current gps coordinates
	'''	
	
	def __init__(self, connection_type = 1, download_dir = "None"):
		'''
		Parameters
		----------
		connection_type : str or int, optional
			The connection type to the drone (default = 1)
			- 'physical' or 0
			- 'controller' or 1
		download_dir : str
			The location drone media will be downloaded (default = "None")
			If none is provided it will download them to /AnafiMedia
			If the directory does not exist it will be created
		'''
		if connection_type == "physical" or connection_type == 0:
			self.drone_ip = "192.168.42.1"		
			self.drone_rtsp_port = os.environ.get("DRONE_RTSP_PORT")
			self.drone_url = "http://{}/".format(self.drone_ip)

		elif connection_type == "controller" or connection_type == 1:
			self.drone_ip = "192.168.53.1"		
			self.drone_rtsp_port = os.environ.get("DRONE_RTSP_PORT", "554")
			self.drone_url = "http://{}:180/".format(self.drone_ip)
		else:
			raise RuntimeError("Illegal object parameter")

		self.drone = olympe.Drone(self.drone_ip)
		if download_dir == "None":
			if os.path.isdir("static") == False:			
				os.mkdir("static")		
			self.download_dir = "static"
		else:
			if os.path.isdir(download_dir) == False:
				os.mkdir(download_dir)
			self.download_dir = download_dir
		
		self.camera = AnafiCamera(self.drone, self.drone_ip, self.drone_rtsp_port, 
			self.drone_url, self.download_dir)
		self.piloting = AnafiPiloting(self.drone)
		self.rth = AnafiRTH(self.drone)
		self.rth.setup_rth()
			
	def connect(self):
		'''
		Establishes a connection with the drone
		'''
		
		assert self.drone.connect(retry = 3)
		print("< Drone Connected >")
	
	def disconnect(self):
		'''
		Breaks the current connection with the drone
		'''

		self.drone.destroy()
		print("< Drone Disconnected >")
		
	def get_drone_coordinates(self):
		'''
		Returns the drone's current gps coordinates
		
		Return
		----------
		coordinates : str[latitude, longitude, altitude]
			list containing the current latitude, longitude, and altitude gps values
		'''
		
		temp = self.drone.get_state(PositionChanged)
		latitude = temp["latitude"]
		longitude = temp["longitude"]
		altitude = temp["altitude"]
		coordinates = [latitude, longitude, altitude]
		return coordinates

	def get_drone_orientation(self):
		'''
		Returns the drone's current orientation (yaw, pitch, roll)
		
		Return
		----------
		orientation : str[yaw, pitch, roll]
			list containing the current yaw, pitch, and roll values
		'''
		
		temp = self.drone.get_state(AttitudeChanged)
		yaw = temp["yaw"]
		pitch = temp["pitch"]
		roll = temp["roll"]
		coordinates = [yaw, pitch, roll]
		return coordinates

	def get_drone_heading(self):
		'''
		Returns the drone's current heading
		
		Return
		----------
		heading : str
			the drone's current heading or yaw value
		'''
		
		temp = self.drone.get_state(AttitudeChanged)
		heading = temp["yaw"]
		return heading
