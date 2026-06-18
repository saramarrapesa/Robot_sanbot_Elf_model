package com.example.robot_application_old;

public interface VisionCallbacks {
    void onRecognitionSuccess(String userId, boolean isRecognized);
    void onRecognitionFailed(String error);
}
