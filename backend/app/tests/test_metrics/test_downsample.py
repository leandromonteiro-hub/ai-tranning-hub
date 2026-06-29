from app.services.metrics.downsample import downsample


def test_downsample_none_and_empty():
    assert downsample(None, 10) == []
    assert downsample([], 10) == []


def test_downsample_keeps_short_series():
    assert downsample([1.0, 2.0, 3.0], 10) == [1.0, 2.0, 3.0]


def test_downsample_buckets_average():
    # 6 pontos para 3 buckets → médias [1.5, 3.5, 5.5]
    assert downsample([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 3) == [1.5, 3.5, 5.5]


def test_downsample_bucket_all_none_is_none():
    out = downsample([None, None, 4.0, 6.0], 2)
    assert out == [None, 5.0]
