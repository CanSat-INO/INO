#include "MainScaffold.h"

int main() {
    MainScaffold module;
    if (module.sampleSensors() != ScaffoldResult::NotImplemented) return 1;
    if (module.calibrate() != ScaffoldResult::NotImplemented) return 1;
    if (module.assessSensorQuality() != ScaffoldResult::NotImplemented) return 1;
    if (module.estimatePose() != ScaffoldResult::NotImplemented) return 1;
    if (module.evaluateRelease() != ScaffoldResult::NotImplemented) return 1;
    if (module.evaluateLanding() != ScaffoldResult::NotImplemented) return 1;
    if (module.manageSeparation() != ScaffoldResult::NotImplemented) return 1;
    if (module.manageDeployment() != ScaffoldResult::NotImplemented) return 1;
    if (module.stepMission() != ScaffoldResult::NotImplemented) return 1;
    if (module.selectMissionMode() != ScaffoldResult::NotImplemented) return 1;
    if (module.navigate() != ScaffoldResult::NotImplemented) return 1;
    if (module.computeGoalBearing() != ScaffoldResult::NotImplemented) return 1;
    if (module.assessStuck() != ScaffoldResult::NotImplemented) return 1;
    if (module.recoverMotion() != ScaffoldResult::NotImplemented) return 1;
    if (module.handleCan() != ScaffoldResult::NotImplemented) return 1;
    if (module.handleTwelite() != ScaffoldResult::NotImplemented) return 1;
    if (module.manageCommand() != ScaffoldResult::NotImplemented) return 1;
    if (module.manageCapture() != ScaffoldResult::NotImplemented) return 1;
    if (module.reconcileTime() != ScaffoldResult::NotImplemented) return 1;
    if (module.restoreState() != ScaffoldResult::NotImplemented) return 1;
    if (module.saveState() != ScaffoldResult::NotImplemented) return 1;
    if (module.logSensors() != ScaffoldResult::NotImplemented) return 1;
    if (module.assessHealth() != ScaffoldResult::NotImplemented) return 1;
    return 0;
}
