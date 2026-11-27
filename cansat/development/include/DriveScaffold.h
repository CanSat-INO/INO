#pragma once
#include "ScaffoldResult.h"

class DriveScaffold {
public:
    ScaffoldResult configureMotorDriver() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult setPwm() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult driveForward() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult driveReverse() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult turn() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult stop() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult manageDeployment() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult trackState() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult handleCan() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult validateCommand() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult checkExpiry() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult safeStop() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult assessFault() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult recover() { return ScaffoldResult::NotImplemented; }
    ScaffoldResult measurePerformance() { return ScaffoldResult::NotImplemented; }
};
