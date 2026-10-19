"""Pure load schedule, independently testable without monkey-patching networking."""


def spike_target(elapsed, peak):
    if elapsed < 120:
        return max(1, peak // 2), 2
    if elapsed < 240:
        return peak, peak
    if elapsed < 540:
        return max(1, peak // 2), peak
    return None
