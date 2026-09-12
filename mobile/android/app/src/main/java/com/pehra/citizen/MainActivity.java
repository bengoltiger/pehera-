package com.pehra.citizen;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final int PERMISSION_REQUEST = 1001;

    @Override
    public void onCreate(android.os.Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestDemoPermissions();
    }

    /**
     * The citizen app uses navigator.geolocation (watchPosition) in the WebView.
     * Android never shows the runtime prompt for that API on its own — it depends
     * on the coarse/fine location permission being granted, so this app asks for
     * it up front (once) instead of waiting for the Bluetooth flow to do it.
     */
    private void requestDemoPermissions() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return;
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                == PackageManager.PERMISSION_GRANTED) return;
        requestPermissions(new String[]{
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
        }, PERMISSION_REQUEST);
    }
}