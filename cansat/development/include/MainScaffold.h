#pragma once
#include "ScaffoldResult.h"

class MainScaffold {
public:
    ScaffoldResult sampleSensors() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult calibrate() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult assessSensorQuality() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult estimatePose() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult evaluateRelease() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult evaluateLanding() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageSeparation() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageDeployment() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult stepMission() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult selectMissionMode() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult navigate() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult computeGoalBearing() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult assessStuck() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult recoverMotion() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult handleCan() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult handleTwelite() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageCommand() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageCapture() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult reconcileTime() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult restoreState() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult saveState() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult logSensors() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult assessHealth() { return ScaffoldResult::NotImplemented; }
};
