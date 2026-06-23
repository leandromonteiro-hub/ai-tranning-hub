from app.services.workout.model import Target, Step, Repeat, StructuredWorkout


def test_structured_workout_roundtrips_through_json():
    w = StructuredWorkout(
        name="Sweet Spot",
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.55, high=0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720,
                     target=Target(type="power_pct_ftp", low=0.88, high=0.93)),
                Step(intensity="rest", duration_s=300,
                     target=Target(type="power_pct_ftp", low=0.50, high=0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600,
                 target=Target(type="open", low=None, high=None)),
        ],
        ftp_watts=250.0,
    )
    dumped = w.model_dump(mode="json")
    restored = StructuredWorkout.model_validate(dumped)
    assert restored.name == "Sweet Spot"
    assert restored.ftp_watts == 250.0
    assert isinstance(restored.elements[1], Repeat)
    assert restored.elements[1].count == 3
    assert restored.elements[0].target.low == 0.55
