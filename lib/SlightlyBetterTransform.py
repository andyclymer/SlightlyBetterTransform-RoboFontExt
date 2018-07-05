from mojo.events import BaseEventTool, addObserver, removeObserver, extractNSEvent, installTool, setActiveEventTool, getActiveEventTool, setActiveEventToolByIndex
import mojo.drawingTools as dt
from lib.tools.defaults import getDefaultColor
from mojo.UI import UpdateCurrentGlyphView
from mojo.extensions import ExtensionBundle
from AppKit import NSColor, NSImage
import math



class KeyWatcherHelper:
    """
    Watch for a keyboard shortcut, and then activate the tool by name
    """
    
    def __init__(self):
        addObserver(self, "keyDown", "keyDown")
        
    def keyDown(self, event):
        event = extractNSEvent(event)
        if event["commandDown"] and event["shiftDown"] and event["keyDown"] == "r":
            currentTool = getActiveEventTool()
            if not currentTool.__class__ == SlightlyBetterTransformTool:
                # Switch to the tool
                setActiveEventTool("SlightlyBetterTransformTool")
            else:
                # The tool was already active, switch back to the Edit tool
                setActiveEventToolByIndex(0)
            
KeyWatcherHelper()



class SlightlyBetterTransformTool(BaseEventTool):
    
    
    """
    Slightly Better Transform
    by Andy Clymer, July 2018
    
    Transform the selection with fewer features than the built-in transform, but with some small improvements:
        
        - Points only round once, you're free to continue transforming the selection without accumulating rounding errors
        - You can select the transform "handles" and use the arrow keys to nudge them around
        - With no handles selected, dragging and nudging will move the selection
        - Shows deltas for how far each face of the transform bounding box moved
        - The transformation bounding box excludes the off-curves, making it easier to measure how far the on-curves moved
    
    """
    
    def becomeActive(self):
        
        self.glyph = None
        self.cachedGlyph = None # A copy of the glyph to use as a reference, to avoid accumulating rounding errors
        
        self.selectionBounds = None # The selection rect that the user is modifying
        self.cachedSelectionBounds = None # The selection rect from the original cached set of points
        self.selectionHandles = None # The handle locaitons on the selectionBounds
        self.selectedHandle = None # Currently selected handle, for nudging and things
        
        # Current state of the transformation
        self.currentOffset = (0, 0)
        self.currentScale = (1, 1)
        
        self.handleNeighbors = {
            "N": ("NW", "NE"), # Previous and next cardinal directions
            "NE": ("N", "E"),
            "E": ("NE", "SE"),
            "SE": ("E", "S"),
            "S": ("SE", "SW"),
            "SW": ("S", "W"),
            "W": ("SW", "NW"),
            "NW": ("W", "N")}
        
        self.selectionColor = self.NSColorToRGBA(getDefaultColor("glyphViewSelectionColor"))
        
        addObserver(self, "glyphChanged", "viewDidChangeGlyph")
        addObserver(self, "glyphDidUndo", "didUndo")
        
        # To help with the Undo
        self.needsUndo = False
        
        # Go ahead and collect the glyph info
        self.glyphChanged(None)
        

    def becomeInactive(self):
        removeObserver(self, "viewDidChangeGlyph")
        removeObserver(self, "didUndo")
        
        
    def getToolbarTip(self):
        return "Slightly Better Transform"
        
        
    def getToolbarIcon(self):
        extBundle = ExtensionBundle("SlightlyBetterTransform")
        toolbarIcon = extBundle.get("SlightlyBetterTransform_ToolbarIcon-2x")
        return toolbarIcon
        
        
    def glyphChanged(self, info):
        self.glyph = CurrentGlyph()
        self.cachedGlyph = self.glyph.copy()
        # If nothing is selected, select all
        if not self.glyph.selection:
            for c in self.glyph.contours:
                for bPt in c.bPoints:
                    bPt.selected = True
        # Update the selection bounds
        self.cachedSelectionBounds = self.getSelectionBounds()
        self.currentOffset = (0, 0)
        self.currentScale = (1, 1)
        self.updateBounds()
        
    
    def updateBounds(self):
        self.selectionBounds = self.getSelectionBounds()
        self.selectionHandles = self.getBoundsHandles(self.selectionBounds)
        
        
    def glyphDidUndo(self, info):
        self.updateBounds()
        
        
    def keyDown(self, event):
        modifiers = self.getModifiers()
        event = extractNSEvent(event)
        arrowDown = True in [event["left"], event["right"], event["up"], event["down"]]
        # If there's a selection:
        if self.selectionBounds:
            if event["keyDownWithoutModifiers"] == "\x1b":
                # Escape key -- deselect handles
                self.selectedHandle = None
                self.updateView()
            elif event["keyDownWithoutModifiers"] == "\t":
                # Tab key and option tab -- rotate the choice of selected handle
                if not self.selectedHandle:
                    self.selectedHandle = "SW"
                elif modifiers["optionDown"]:
                    self.selectedHandle = self.handleNeighbors[self.selectedHandle][0]
                else: self.selectedHandle = self.handleNeighbors[self.selectedHandle][1]
                self.updateView()
            elif arrowDown:
                # Arrow keys -- move the selection
                delta = (0, 0)
                value = 1
                if modifiers["shiftDown"]:
                    value *= 10
                if modifiers["commandDown"]:
                    value *= 10
                if event["left"]:
                    delta = (-value, 0)
                elif event["right"]:
                    delta = (value, 0)
                elif event["up"]:
                    delta = (0, -value)
                elif event["down"]:
                    delta = (0, value)
                self.glyph.prepareUndo("Transform!")
                self.moveSelection(delta)
                self.glyph.performUndo()
                
        
    def mouseDown(self, point, clickCount):
        self.selectedHandle = None
        # Find the closest handle to the mouseDown point
        if self.selectionBounds:
            handleDistances = []
            for handle, handleLoc in self.selectionHandles.items():
                handleDistances += [{"handle":handle, "handleLoc":handleLoc, "dist":self.distance((point.x, point.y), handleLoc)}]
            sortedByDist = sorted(handleDistances, key=lambda k: k["dist"])
            if sortedByDist[0]["dist"] <= 10:
                self.selectedHandle = sortedByDist[0]["handle"]
        # And set a flag if the mouse went down in the box
        self.mouseDownInBounds = self.pointInBounds((point.x, point.y), self.selectionBounds)
        
        
    def mouseUp(self, point):
        if self.needsUndo:
            self.glyph.performUndo()
            self.needsUndo = False
            
            
    def mouseDragged(self, point, delta):
        if self.selectedHandle or self.mouseDownInBounds:
            if not self.needsUndo:
                self.glyph.prepareUndo("Transform")
                self.needsUndo = True
            self.moveSelection(delta)
            
    
    def moveSelection(self, delta):
        self.didTransform = True
        if self.selectedHandle:
            # A handle is selected
            # Change the size of the selectionBounds
            if "W" in self.selectedHandle:
                self.selectionBounds[0] += delta[0]
            elif "E" in self.selectedHandle:
                self.selectionBounds[2] += delta[0]
            if "S" in self.selectedHandle:
                self.selectionBounds[1] -= delta[1]
            elif "N" in self.selectedHandle:
                self.selectionBounds[3] -= delta[1]
        else:
            # Nothing selected, drag the selection
            self.selectionBounds[0] += delta[0]
            self.selectionBounds[2] += delta[0]
            self.selectionBounds[1] -= delta[1]
            self.selectionBounds[3] -= delta[1]
        # Round the bounds locations
        self.selectionBounds = [
            int(round(self.selectionBounds[0])),
            int(round(self.selectionBounds[1])),
            int(round(self.selectionBounds[2])),
            int(round(self.selectionBounds[3]))]
        # Update the handles to their new location
        self.selectionHandles = self.getBoundsHandles(self.selectionBounds)
        # Get the updated offset and scale
        self.currentOffset, self.currentScale = self.getBoundsOffsetAndScale()
        # And the location that the scale offset is calculated from, bottom left of the bounds
        origin = self.cachedSelectionBounds[0:2]
        # 
        # Transform!
        # Copy the cached glyph...
        tempGlyph = self.cachedGlyph.copy()
        for contourIdx, contour in enumerate(self.glyph.contours):
            for bPointIdx, bPoint in enumerate(contour.bPoints):
                if bPoint.selected:
                    # Transform the point in the cached glyph
                    tempBPoint = tempGlyph.contours[contourIdx].bPoints[bPointIdx]
                    tempBPoint.scaleBy(self.currentScale, origin=origin)
                    tempBPoint.moveBy(self.currentOffset)
                    # Apply the moves to the current glyph
                    bPoint.anchor = tempBPoint.anchor
                    bPoint.bcpIn = tempBPoint.bcpIn
                    bPoint.bcpOut = tempBPoint.bcpOut
        self.glyph.changed()
        # Redraw!
        self.updateView()
        
    
    def updateView(self):
        UpdateCurrentGlyphView()
        
                
    def draw(self, scale):
        circleRadius = 12 * scale
        if self.selectionBounds:
            # The selection rect
            rect = (self.selectionBounds[0], 
                    self.selectionBounds[1], 
                    self.selectionBounds[2]-self.selectionBounds[0], 
                    self.selectionBounds[3]-self.selectionBounds[1])
            dt.save()
            dt.font("Lucida Grande")
            dt.fontSize(11*scale)
            # Circles around opoints
            dt.fill(None)
            dt.stroke(*self.selectionColor[0:3], 0.25)
            dt.strokeWidth(7*scale)
            for point in self.glyph.selection:
                dt.oval(point.x-circleRadius, point.y-circleRadius, circleRadius*2, circleRadius*2)
            # Bounding box
            dt.strokeWidth(1*scale)
            dt.stroke(*self.selectionColor)
            dt.rect(*rect)
            # Boxes on the handles
            for handle, handleLoc in self.selectionHandles.items():
                dt.strokeWidth(2*scale)
                dt.stroke(*self.selectionColor[0:3], 1)
                if handle == self.selectedHandle:
                    dt.fill(*self.selectionColor[0:3], 1)
                    boxRadius = 6 * scale
                else: 
                    dt.fill(None)
                    boxRadius = 4 * scale
                # Draw the handle
                dt.rect(handleLoc[0]-boxRadius, handleLoc[1]-boxRadius, boxRadius*2, boxRadius*2)
                # Draw the handle delta text
                dt.stroke(None)
                dt.fill(*self.selectionColor[0:3], 1)
                if handle == "N":
                    dt.textBox(
                        str(int(self.selectionBounds[3]-self.cachedSelectionBounds[3])), 
                        (handleLoc[0]-(100*scale), handleLoc[1], (200*scale), (20*scale)), 
                        align="center")
                if handle == "S":
                    dt.textBox(
                        str(int(self.selectionBounds[1]-self.cachedSelectionBounds[1])), 
                        (handleLoc[0]-(100*scale), handleLoc[1]-(30*scale), (200*scale), (20*scale)), 
                        align="center")
                if handle == "E":
                    dt.textBox(
                        str(int(self.selectionBounds[2]-self.cachedSelectionBounds[2])), 
                        (handleLoc[0]+(10*scale), handleLoc[1]-(11*scale), (200*scale), (20*scale)), 
                        align="left")
                if handle == "W":
                    dt.textBox(
                        str(int(self.selectionBounds[0]-self.cachedSelectionBounds[0])), 
                        (handleLoc[0]-(211*scale), handleLoc[1]-(11*scale), (200*scale), (20*scale)), 
                        align="right")
            # Draw the scale text
            dt.stroke(None)
            dt.fill(*self.selectionColor[0:3], 1)
            infoText = "Scale: %.3f %.3f" % self.currentScale
            dt.text(infoText, self.selectionBounds[2]+(10*scale), self.selectionBounds[1]-(20*scale))
            dt.restore()
    
    
    def NSColorToRGBA(self, nsColor):
        # Helper to turn a NSColor into a (r, g, b, a) tuple
        return (nsColor.redComponent(),
            nsColor.greenComponent(),
            nsColor.blueComponent(),
            nsColor.alphaComponent())
            
            
    def interpolate(self, f, a, b):
        return a + (b - a) * f
        
        
    def distance(self, loc1, loc2):
        (x1, y1) = loc1
        (x2, y2) = loc2
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

            
    def getSelectionBounds(self):
        # Returns the bounding box of the selected points (not counting off-curves)
        rect = None
        if self.glyph:
            if self.glyph.selection:
                allX = []
                allY = []
                for point in self.glyph.selection:
                    allX.append(point.x)
                    allY.append(point.y)
                if not allX:
                    return None
                allX.sort()
                allY.sort()
                rect = [allX[0], allY[0], allX[-1], allY[-1]]
        return rect
        
        
    def getBoundsHandles(self, rect):
        # Returns a dictionary of handles along the edge of a bounding box rect
        if not rect:
            return None
        else:
            handles = { "SW": (rect[0], rect[1]),
                    "NW": (rect[0], rect[3]),
                    "SE": (rect[2], rect[1]),
                    "NE": (rect[2], rect[3]),
                    "SW": (rect[0], rect[1]),
                    "W":  (rect[0], self.interpolate(0.5, rect[1], rect[3])),
                    "E":  (rect[2], self.interpolate(0.5, rect[1], rect[3])),
                    "S":  (self.interpolate(0.5, rect[0], rect[2]), rect[1]),
                    "N":  (self.interpolate(0.5, rect[0], rect[2]), rect[3])}
            return handles
    
    
    def getBoundsOffsetAndScale(self):
        # Compares two bounding boxes to determine offset and scale
        if self.selectionBounds and self.cachedSelectionBounds:
            cachedW = self.cachedSelectionBounds[2] - self.cachedSelectionBounds[0]
            cachedH = self.cachedSelectionBounds[3] - self.cachedSelectionBounds[1]
            w = self.selectionBounds[2] - self.selectionBounds[0]
            h = self.selectionBounds[3] - self.selectionBounds[1]
            offsetX = self.selectionBounds[0] - self.cachedSelectionBounds[0]
            offsetY = self.selectionBounds[1] - self.cachedSelectionBounds[1]
            if cachedW == 0:
                scaleW = 0
            else: scaleW = w / cachedW
            if cachedH == 0:
                scaleH = 0
            else: scaleH = h / cachedH
            return (offsetX, offsetY), (scaleW, scaleH)
        else: return None
        
        
    def pointInBounds(self, point, bounds):
        if bounds:
            return bounds[0] < point[0] < bounds[2] and bounds[1] < point[1] < bounds[3]
        else: return False
    

installTool(SlightlyBetterTransformTool())
