#pragma once
#include "ScaffoldResult.h"

class CameraScaffold {
public:
    ScaffoldResult configureCamera() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult captureFrame() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult associateStereoPair() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult trackCaptureMetadata() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult handleCan() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult connectWifi() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult transferImage() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageBuffer() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult recover() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult measurePerformance() { return ScaffoldResult::NotImplemented; }
};
