import numpy as np
import cv2

#code for perspective transform inspired by Adrian Rosebrock's code here: https://pyimagesearch.com/2014/08/25/4-point-opencv-getperspective-transform-example/

def ptsToClockwiseRect(pts):
    #new array of four x,y coordinates, initialized to zero.
    rect = np.zeros((4,2),dtype="float32")
    #np sum will add the x,y vals, ie. Axis 1 of an array of 4 x,y pts.
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2]= pts[np.argmax(s)]
    #there is a chance the middle two points will have the same sum, so we can't figure them this way. 
    #we need to instead figure the biggest distance between points. 
    #I think this makes some assumptions about our rectangle not being too distorted.
    d = np.diff(pts,axis=1)
    rect[1]=pts[np.argmin(d)]
    rect[3]=pts[np.argmax(d)]
    return rect

def perspectiveTransform(image,pts):
    rect = ptsToClockwiseRect(pts)
    (tl, tr, br, bl) = rect #these are the points from the rectangle in order.
    #calculate the new image width which will be the 
    #maximum between the distance between the top points or the distance between the bottom ones.
    #distance = root(a^2+b^2). Honestly, we could just convert these guys into vectors and get the length.
    widthbrbl = np.sqrt((br[0]-bl[0])**2 + (br[1]-bl[1])**2)
    widthtrtl = np.sqrt((tr[0]-tl[0])**2 + (tr[1]-tl[1])**2)
    maxWidth = max(int(widthbrbl),int(widthtrtl))
    #do the same for the height.
    heighttrbr = np.sqrt((tr[0]-br[0])**2 + (tr[1]-br[1])**2)
    heighttlbl = np.sqrt((tl[0]-bl[0])**2 + (tl[1]-bl[1])**2)
    maxHeight = max(int(heighttrbr),int(heighttlbl))
    #construct a new array of pixels of the new dimensions into which the old image will be stretched.
    dst = np.array([
        [0,0],
        [maxWidth-1,0],
        [maxWidth-1,maxHeight-1],
        [0,maxHeight-1]
    ], dtype="float32")
    transformmatrix = cv2.getPerspectiveTransform(rect,dst)
    newpixels = cv2.warpPerspective(image,transformmatrix,(maxWidth,maxHeight))
    return newpixels

