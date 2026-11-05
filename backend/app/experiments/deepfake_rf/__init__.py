"""Random Forest experiment on features from the existing DeepGuard service.

This package does not change production predictions or the V1 aggregation rule.
"""

FEATURE_SCHEMA_VERSION = "deepfake_rf_features_v1"
MODEL_VERSION = "deepfake_rf_v2"
MEASUREMENT_SOURCE = "deepguard_frame_results"
