# HD 6XX calibration experiments

All three profiles use the same stock Sennheiser HD 6XX measurement from oratory1990 and the same target-neutral PrecisEQ zero target.

- HD 6XX: reference profile, AutoEq generator defaults.
- HD 6XX Hi-Res 2Hz: 2 Hz FIR resolution, 1/24-oct main smoothing, 1-oct treble smoothing.
- HD 6XX Extreme 1Hz: 1 Hz FIR resolution, 1/24-oct main smoothing, 1/2-oct treble smoothing.

We tested 1/48-oct main smoothing, but the oratory1990 source sampling is not dense enough for AutoEq's Savitzky-Golay smoother at that window size. 1/24 octave is therefore the practical source-resolution floor for this measurement in AutoEq 4.1.2.

The listening target remains a separate PrecisEQ in-app stage.
