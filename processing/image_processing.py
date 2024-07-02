""" This module contains code that takes a 2D image and process it in prerparation for building a 
collection of such images into a 3D Model.
The code here does automatically, what might otherwise be done in photoshop and lightroom. 
It removes lens distortion and vignetting, changes
white balance, and converts the document to a tiff. The functions here are called from elsewhere: namely photogrammetryScripts.py
Author: Kea Johnston, June 2024
"""

import os
from pathlib import Path
import shutil
from time import perf_counter
import subprocess
import imageio
import rawpy
import lensfunpy
import numpy as np
import cv2
from PIL import Image as PILImage
from PIL import ExifTags
from util import util
from processing import processingTools


def findGray(colorcarddatacv2):
    """Given an array of pixels corresponding to a color card, find the second gray box from the center.
    This basically just finds the center point and counts two swatches up and over. It doesn't do any sort of special color
    detection stuff.
    
    Parameters:
    ---------------
    colorcarddatacv2 - an array of pixels.
    """

    h,w,rgb = colorcarddatacv2.shape
    midpoint = [int(w/2),int(h/2)]
    #there are four squares per row on a color card. 
    halfsquare = int(w/8)
    #our gray square ought to be about a square and a half up and to the right from the centerpoint.
    graycoords = [midpoint[0]+3*halfsquare,midpoint[1]-3*halfsquare]
    print(f"width:{w},height:{h},square dimensions:{halfsquare*2}, gray location:{graycoords}")
    graypoint = colorcarddatacv2[graycoords[0],graycoords[1]]
    print(f"color {graypoint} at coords: {graycoords}")
    return graypoint


def get_color_card_from_image(colorcardimage: str): 
    """
    Detects Aruco markers around a color card in a picture, and does a perspective transform on them so that they form a rectangular image.
    The model for this code is here: https://pyimagesearch.com/2021/02/15/automatic-color-correction-with-opencv-and-python/
    
    Parameters:
    -----------------
    colorcardimage: path to an image with a color card and aruco markers in it.

    returns: a numpy array of pixels (numpy.Matlike) representing the color card.

    """
    markerdict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    arucoparams = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(markerdict,arucoparams)
    corners, ids, rejected = detector.detectMarkers(colorcardimage)
    ids = ids.flatten()
    print("found markers {ids}")
    try:
        #basically get the index in the ids array of each marker id. 
        #The corner coordinates of the marker will have the same index in the 
        #multidimensional "corners" array. Get the outermost coordinate for each item in the array 
        # we will use these to straighten the color card. The order of the ids is arbitrary based on how I made the card.
        idindex = np.squeeze(np.where(ids==2))
        topleft = np.squeeze(corners[idindex])[0]
        print("Got topleft")
        idindex = np.squeeze(np.where(ids==3))
        topright = np.squeeze(corners[idindex])[1]
        print("Got topright")
        idindex = np.squeeze(np.where(ids==0))
        bottomright = np.squeeze(corners[idindex])[2]
        print("Got bottomright")
        idindex = np.squeeze(np.where(ids==1))
        bottomleft = np.squeeze(corners[idindex])[3]
        print("Got bottomleft")
        card = processingTools.perspective_transform(colorcardimage,np.array([topleft,topright,bottomright,bottomleft]))
        return card
    except Exception as e:
        print(e)
        print(f"Could not find four markers in the color card iamge. Markers found were: {ids}. Aborting.")
        return None
    
def build_masks(imagefolder,outputpath,mode,config):
    if mode == util.MaskingOptions.MASK_DROPLET:
        build_masks_with_droplet(imagefolder,outputpath,config)

def build_masks_with_droplet( imagefolder, outputpath, config):
    """Builds masks for a folder of images using a photoshop droplet specified in config.json.
    The droplet runs a context aware select on the central pixel of an image and then dumps the mask in a temp directory. 
    This directory is set in photoshop when creating the droplet, but it must be configured in config.json so that the script
    knows where to look for the masks in order to copy them to their final destination. The format saved by the droplet is set in the droplet.
    It must also be configured in config.json->photogrammetry->mask_ext in order for the script to recognize the masks when importing
    them into Metashape.
    
    Parameters:
    ---------------------
    imagefolder: the folder where the tif files that need to be masked are stored.
    outputpath: the folder where the masks will ultimately be stored.
    config: a dictionary of config values--the whole dictionary under config.json->processing.
    """
    starttime = perf_counter()
    dropletpath = util.get_config_for_platform(config["Masking_Droplet"])
    dropletoutput = util.get_config_for_platform(config["Droplet_Output"])
    if not dropletpath:
        print("Cannot build mask with a non-existent droplet. Please specify the droplet path in the config under processing->Masking_Droplet.")
        return
    else:
        print(f" Using Droplet at {dropletpath}")
    maskdir = outputpath
    if not os.path.exists(maskdir):
        os.mkdir(maskdir)
    if not os.path.exists(dropletoutput):
        os.mkdir(dropletoutput)
    #droplet should dump files in c:\tempmask or \tempmask
    subprocess.run([dropletpath,imagefolder],check = False)
    with os.scandir(dropletoutput) as it: #scans through a given directory, returning an interator.
        for f in it:
            if os.path.isfile(f):
                oldpath = f.path
                filename = f.name
                shutil.move(oldpath,os.path.join(maskdir,filename))
    shutil.rmtree(dropletoutput)
    stoptime = perf_counter()
    print(f"Build Mask using a droplet in {stoptime-starttime} seconds.")

def process_image(filepath: str, output: str, config: dict):
    """Runs non-filter corrections on a file format and then exports it as a tiff
    
    Checks to see if a file is a canon RAW file (CR2), and converts the file to tiff. Then, opens the file and with imageio 
    and does lens profile corrections and vignette removal. Eventually this function will also do white balance.
    
    Parameters
    -------------
    filepath : the path to an image file.
    output : the path where you want the new tiff file to be written.
    config : a dictionary of config values. These are found in the config.json file under "processing", which is the dict that gets passed in.

    """
    processedpath = ""
    if not os.path.exists(output):
        os.mkdir(output)    
    if not filepath.upper().endswith(config["Destination_Type"].upper()):
        if filepath.upper().endswith("CR2"):
            #exif = get_exif_data(filepath)
            if config["Destination_Type"].upper() == ".TIF":
                processedpath = convert_CR2_to_TIF(filepath,output,config)
            elif config["Destination_Type"].upper() == ".JPG":
                processedpath = convertToJPG(filepath,output)
        elif filepath.upper().endswith("TIF"):
            if config["Destination_Type"].upper() == ".JPG":
                processedpath = convertToJPG(filepath,output)
    return processedpath 


def lens_profile_correction(tifhandle ,config: dict, exif: dict):
    """Does lens profile correction and vignetting removal on an image using the FNumber and Focal length from the Exif file.
     
    Parameters:
    ------------
    tifhandle: The handle to a file read by imageio.
    config: the dictionary of values under "processing" in config.json.
    exif: a dictionary of exif metadata.

    returns: an array of modified pixels.
    """
    #do lens profile correction This code was borrowed from here: https://pypi.org/project/lensfunpy/
    clprofile = util.get_camera_lens_profile(config["Camera"],config["Lens"])
    lensdb = lensfunpy.Database()
    #both of these return a list, the first item of which should be our camera. If not, we need to be more specific.
    cam = lensdb.find_cameras(clprofile["camera"]["maker"],clprofile["camera"]["model"])[0]
    lens = lensdb.find_lenses(cam,clprofile["lens"]["maker"],clprofile["lens"]["model"])[0]
    #get data needed for calc from exif data
    focal_length = exif["FocalLength"] if "FocalLength" in exif.keys() else 0
    aperture = exif["FNumber"] if "FNumber" in exif.keys() else 0
    if focal_length ==0 or aperture ==0:
        print(f"WARNING: Can't do profile corrections, because there is no value for aperture or f-number in the exif data of the photo.")
        return tifhandle
    distance = 1.0 #can't think of a great way to calculate this so I'm going to hardcode it since it's about a meter in person and with the ortery.
    img_width = tifhandle.shape[1]
    img_height = tifhandle.shape[0]
    modifier = lensfunpy.Modifier(lens,cam.crop_factor,img_width,img_height)
    print(f"focal_length = {focal_length}, aperture ={aperture}, distance={distance}, cam:{cam}, lens:{lens}")
    modifier.initialize(focal_length,aperture,distance,pixel_format = tifhandle.dtype.type ) #demo code has this as just dtype, but it has a keyerror exception.
    undist_coords = modifier.apply_geometry_distortion()
    newimg = cv2.remap(tifhandle,undist_coords, None, cv2.INTER_LANCZOS4)
    if not modifier.apply_color_modification(newimg):
        print("WARNING: Failed to remove vignetting.")
    return newimg

def convert_CR2_to_DNG(input,output,config):
    """ Uses the Adobe DNG converter to convert CR2 or NEF files to DNG.

    Parameters:
    -------------------------
    input: path to a CR2 file.
    output: the path where you want the TIF saved.
    config: the dictionary of values under "processing" in the config.json file"
    """

    outputcmd = f"-d \"{output}/\""
    converterpath = util.get_config_for_platform(config["DNG_Converter"])
    subprocess.run([converterpath,"-d",output,"-c", input], check = False)

def get_exif_data(filename: str) -> dict:
    """ Gets the Exif data from an image file if it exists, and returns a dictionary of key value pairs.
    
        Data nested under IFD Codes will be flattened out and will be on the same level as the
        rest of the exif data in the returned dictionary.

        Parameters:
        ------------------
        filename: The path to the image file whose exif data needs to be retreived.

        Returns: A dictionary of key value pairs.
    """
    exif = {}
    skiplist=["MakerNote","UserComment"] #These are not needed and are encoded anyway.
    with PILImage.open(filename,'r') as pi:
        exif = pi.getexif()
        IFD_CODES = {i.value: i.name for i in ExifTags.IFD}
        for code, val in exif.items():
            if code in IFD_CODES:
                propname = IFD_CODES[code]
                ifd_data = exif.get_ifd(code)
                for nk,nv in ifd_data.items():
                    nested_tag = ExifTags.GPSTAGS.get(nk,None) or ExifTags.TAGS.get(nk,None) or nk
                    if nested_tag in skiplist:
                        continue
                    exif[nested_tag]=nv
            else:
                tagname = ExifTags.TAGS.get(code,code)
                exif[tagname]=val
    return exif

def convert_CR2_to_TIF(input: str ,output: str, config: dict) -> str:
    """Converts a Canon RAW file to a TIF using the Rawpy library
    
    Currently sets the white balance to the camera white balance. TODO: Allow the white balance to be taken from a gray card.
    
    Parameters:
    ------------------
    input: path to a CR2 file.
    output: the path where you want the TIF saved.
    config: the dictionary of values under "processing" in the config.json file.

    returns: the full path and filename of the new tif file.
    """
    starttime = perf_counter()
    fn = Path(input).stem
    outputname = os.path.join(output,fn+".tif")
    
    with rawpy.imread(input) as raw:
        rgb = raw.postprocess(use_camera_wb=True)
        imageio.imsave(outputname,rgb)
    stoptime = perf_counter()
    print(f"Converted CR2 to TIF in {stoptime-starttime} seconds")
    return outputname

def convertToJPG(input: str, output: str) -> str:
    """Converts an image file to a high quality JPG.
    Parameters:
    ----------------
    input: full path to an image file.
    output: the directory where you want the output file.

    returns: the full path to the resulting tiff file.

    """
    fn = Path(input).stem #get the filename.
    ext = os.path.splitext(input)[1].upper()
    outputname = os.path.join(output,fn)
    if ext ==".CR2":
        with rawpy.imread(input) as raw:
            rgb = raw.postprocess(use_camera_wb=True)
            imageio.imwrite(f"{outputname}.jpg",rgb)
    else:
        try:
            f=PILImage.open(input)
            f.save(f"{outputname}.jpg",quality=95)
        except Exception as e:
            raise e
    return outputname
