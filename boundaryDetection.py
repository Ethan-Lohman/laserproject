import cv2
import numpy as np
from pygame import mixer
import time

mixer.init()
alert = mixer.Sound('alert.wav') #alert sound for when an intrusion occurs

output_width = 1920 
output_height = 1080
scale = 1.0
PAN_STEP = 20 # number of pixels to shift when panning with arrow keys, adjust as needed for finer or coarser control
pan_x = 0   # positive = shift right
pan_y = 0   # positive = shift down

y1 = 650 # CROP DIMENSIONS 
y2 = 1080
x1 = 450 
x2 = 1325

cap = cv2.VideoCapture(0, cv2.CAP_V4L2) 
cap.set(cv2.CAP_PROP_FRAME_WIDTH, output_width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, output_height)
cap.set(cv2.CAP_PROP_BRIGHTNESS, 20) #dims brightness (white background blew image out)
cap.set(cv2.CAP_PROP_FPS, 15) #FPS limiter
if not cap.isOpened():  
    print("Cannot open camera")
    exit()

orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

def get_crop_dimensions(): #Helper function to determine new crop dimensions - file will be on Raspi 
    while True:  
        ret, frame = cap.read()
        if not ret:
            break
        crop_height = int(orig_height / scale)
        crop_width = int(orig_width / scale)

        center_y = orig_height // 2 + pan_y
        center_x = orig_width // 2 + pan_x

        y1 = max(0, center_y - crop_height // 2)
        y2 = min(orig_height, center_y + crop_height // 2)
        x1 = max(0, center_x - crop_width // 2)
        x2 = min(orig_width, center_x + crop_width // 2)

        cropped_frame = frame[y1:y2, x1:x2]
        zoomed_frame = cv2.resize(cropped_frame, (output_width, output_height), interpolation=cv2.INTER_CUBIC)

        cv2.putText(zoomed_frame, f"Zoom: {scale:.1f}x   Pan: ({pan_x}, {pan_y})", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow('Zoom & Pan Setup (Arrows + / -, ENTER to start monitoring)', zoomed_frame)

        key = cv2.waitKey(1) & 0xFF

        if key == 13:        # ENTER key
            cv2.destroyAllWindows()
            with open("zoom_settings.txt", "w") as f:
                f.write(f"Final Zoom Settings:\n")
                f.write(f"Scale: {scale:.2f}x\n")
                f.write(f"Crop Width: {crop_width} pixels\n")
                f.write(f"Crop Height: {crop_height} pixels\n")
                f.write(f"Output Width: {output_width} pixels\n")
                f.write(f"Output Height: {output_height} pixels\n")
                f.write(f"Pan Offset: ({pan_x}, {pan_y})\n")
                f.write(f"Crop Region: x1={x1}, y1={y1}, x2={x2}, y2={y2}\n")
            break
        elif key == ord('+') or key == ord('='):
            scale += 0.1
        elif key == ord('-') or key == ord('_'):
            scale = max(1.0, scale - 0.1)
        elif key == 81 or key == ord('a'):   # Left arrow
            pan_x = max(-orig_width//2 + 50, pan_x - PAN_STEP)
        elif key == 83 or key == ord('d'):   # Right arrow
            pan_x = min(orig_width//2 - 50, pan_x + PAN_STEP)
        elif key == 82 or key == ord('w'):   # Up arrow
            pan_y = max(-orig_height//2 + 50, pan_y - PAN_STEP)
        elif key == 84 or key == ord('s'):   # Down arrow
            pan_y = min(orig_height//2 - 50, pan_y + PAN_STEP) 



ret, first_frame = cap.read() 
if not ret: 
    print("Cannot read from camera")
    exit()
    
zoomed_frame = first_frame[y1:y2, x1:x2] #crop the first frame to the zoomed area for processing
display = zoomed_frame.copy()
gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY) #convert image to grayscale
blur = cv2.GaussianBlur(gray, (3, 3), 1.0) #apply Gaussian blur to reduce noise and smooth image
def auto_canny(image, sigma=0.25):   # Lower sigma = more sensitive
    v = np.median(image)
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    return cv2.Canny(image, lower, upper, apertureSize=5, L2gradient=True)

edges = auto_canny(blur) #canny edge detection to auto find edges

# Connect broken/weak edges 
kernel = np.ones((3,3), np.uint8)
edges = cv2.dilate(edges, kernel, iterations=1)   # connect gaps
contours, _ = cv2.findContours(edges, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE) #find contours in the edge-detected image

safe_areas = []
center_points = []
mask = None

if contours:
    sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True) #sort contours by area in descending order
    
    # Get up to 15 largest contours if they meet the threshold and aren't duplicates
    last_area = None
    for i in range(len(sorted_contours)):
        area = cv2.contourArea(sorted_contours[i]) #get area of the contour
        if area > 75: #needed to prevent duplicate contours
            m = cv2.moments(sorted_contours[i])
            if m["m00"] != 0: #calculate the center of the contour to prvent duplicates 
                cX = int(m["m10"] / m["m00"])
                cY = int(m["m01"] / m["m00"])
                center = (cX, cY)
                duplicate = False
                for pt in center_points:
                    dist = np.sqrt((cX - pt[0])**2 + (cY - pt[1])**2)
                    if dist < 10:  #if the center of the contour is within 10 pixels of a previously detected contour, consider it a duplicate
                        duplicate = True
                        break
                if duplicate: #skips duplicate contours but checks if the area is significantly different to prevent missing valid boundaries that are close together
                    print(f"Skipping duplicate contour at center: {center}")
                    if abs(area - last_area) / last_area > 0.1:
                        safe_areas.append(sorted_contours[i])
                        print(f"Boundary {len(safe_areas)} detected with contour area: {area}")
                        last_area = area
                        if len(safe_areas) >= 15:
                            break
                    continue
                center_points.append(center) #add the center of the contour to the list of detected centers to prevent future duplicates
            if not duplicate: #append the contour to the list of safe areas if it's not a duplicate and meets the area threshold
                safe_areas.append(sorted_contours[i])
                print(f"Boundary {len(safe_areas)} detected with contour area: {area}")
                last_area = area
                if len(safe_areas) >= 15:
                    break
    
    if safe_areas:
        mask = np.ones(display.shape[:2], dtype=np.uint8)   # Use cropped size
        cv2.fillPoly(mask, safe_areas, 0)
        
        viz = display.copy() #visualization of the detected boundaries for testing confirmation.
        # cv2.drawContours(viz, safe_areas, -1, (0, 255, 0), 3)
        # cv2.imshow('Safe Areas - INSIDE track should be filled', viz) #UNCOMMENT TO VISUALIZE THE DETECTED BOUNDARIES
        # cv2.waitKey(0)
    else:
        print("No significant contours found - using entire frame (no boundary)")
        mask = np.ones(first_frame.shape[:2], dtype=np.uint8) * 255
else:
    print("No significant contours found - using entire frame (no boundary)")
    mask = np.ones(first_frame.shape[:2], dtype=np.uint8) * 255

videoFeed = cv2.createBackgroundSubtractorKNN( #create a background subtractor object using KNN algorithm for motion detection
    history=300,           
    dist2Threshold=400,    
    detectShadows=False
)

print("Monitoring started. Press ESC or 'q' to quit.")

last_alert_time = 0  # Track last alert time to prevent spam

while True:
    ret, frame = cap.read()
    if not ret:
        break
    display = frame.copy()
    crop_height = int(orig_height / scale) #crop image, based on zoom level
    crop_width = int(orig_width / scale)
    center_y = orig_height // 2 + pan_y
    center_x = orig_width // 2 + pan_x
    cropped_frame = display[y1:y2, x1:x2] #crop the frame to the zoomed area for processing, this allows us to maintain a high resolution for motion detection while only processing a smaller area of the frame, improving performance
    zoomed_frame = cv2.resize(cropped_frame, (output_width, output_height), interpolation=cv2.INTER_CUBIC) #
    
    vfmask = videoFeed.apply(zoomed_frame) #apply the background subtractor to the zoomed frame to get a foreground mask that highlights areas of motion
    mask_resized = cv2.resize(mask, (output_width, output_height), interpolation=cv2.INTER_NEAREST) #resize the mask to match the zoomed frame size, using nearest neighbor interpolation to preserve the binary nature of the mask (safe areas vs non-safe areas)
    motion_inside = cv2.bitwise_and(vfmask, vfmask, mask=mask_resized) #use the defined mask to isolate motion that occurs outside the safe areas

    motion_pixels = cv2.countNonZero(motion_inside) #count the number of motion pixels, outside the safe zones
    motion_level = motion_pixels / (zoomed_frame.shape[0] * zoomed_frame.shape[1]) * 100 #calculate percentage of motion pixels relative to the total frame size to determine if it exceeds the intrusion threshold

    if safe_areas:
        cv2.drawContours(zoomed_frame, safe_areas, -1, (0, 255, 0), 2) #draw the detected boundaries on the zoomed frame for visualization REMOVE FOR FINAL VERSION, JUST FOR TESTING PURPOSES

    if motion_level > .025:    #intrusion if more than 0.05% of the pixels in the zoomed frame are detected as motion outside the safe areas
        cv2.putText(zoomed_frame, "INTRUSION DETECTED!", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 255), 4)
        current_time = time.time()
        if current_time - last_alert_time > 2:  # Play alert only once every 2 seconds
            alert.play()
            last_alert_time = current_time
        
    else:
        cv2.putText(zoomed_frame, "Safe", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    
    #cv2.imshow('Zoomed Video (ESC or q to quit)', zoomed_frame) VISUALIZATION OF TRACK BOUNDARYS AND INTRUSION DETECTION, UNCOMMENT TO TEST

    key = cv2.waitKey(1) & 0xFF #exit conditions
    if key == 27 or key == ord('q'): 
        break

cap.release() #release the video capture object and close all OpenCV windows to clean up resources when the program is exited
cv2.destroyAllWindows()