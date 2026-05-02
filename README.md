# 2025-26-TeamLaser

A UI that allows the control of a projection system for the UINDY RBASOE ENGR 196 Robotics Competitions

# Website IP:

http://10.40.97.7/

# Wifi

UIndyEngineering

# New Pi Setup/Ansible

Running the ansible code will setup the pi

- sudo apt install ansible
- clone or ssh the files onto pi
- cd 2025-26-TeamLaser/ansible
- ansible-playbook -i inventory.ini site.yml --ask-become-pass -k
- sudo reboot

This will setup the system on a fresh raspberry pi, and rebooting will ensure the system boots to the correct ip and the backend starts.

# Website

To access the website:

- Connect to the UindyEngineering Wifi
- Go to http://10.40.97.7/

# Website Control (Top to Bottom)

Adjust Image Scale

- Slide the scale to the scale percentage of the original image.
- Textbox to the right to type in the exact scale you wish.

Track Selector + Projecting

- Click the dropdown menu to select the track you wish.
- Click project to project that track with any customization you have.

Upload New Image

- Click upload image to bring a file from your computer to the server.
- Must put in the pin in the right textbox to be able to upload to the server.
- Click upload new image.

Projector - On / Off

- Remotely turn the projector display On and Off.
- Does not turn off the Raspberry Pi.

Stopwatch

- Start, begins / resumes the stopwatch.
- Stop, stops the stopwatch.
- Reset, resets the stopwatch to zero.

Keystone Correction

- Select the Keystone Calibrator to open the menu.
- You can drag the red dots to adjust the distortion on the track image to correct any distortions.
- Save Keystone - Will save how you set it, so when you select this image again you won't have to do the keystone correction again.
- Reset - Resets the dots / Keystone Correction to the default value.
- Enable Live Projection - Will allow you to drag the dots and edit the keystone correction in live time.

# Troubleshooting

System is not turning on.

- On the control website, press turn off, and then turn on. If the website is down, please skip this step.
- Unplug Raspberry PI and plug it back in. To tell if the Raspberry PI on, there should be a bright red light on.
- If the Raspberry PI is not turning on, then look up manuals on how to fix said Raspberry PI.

Projection is wonky looking.

- This issue is fixed by going into the keystone calibration menu, and pressing reset and save, then projecting again.

Website is not loading.

- Make sure you are login to the Uindy Engineering Wifi
- Make sure the website address is correct: http://10.40.97.7/
- Make sure the Raspberry PI is on. (You will see a red light shining on the projector mount)

<!-- We will be adding the directions in this file once system is more mature -->
