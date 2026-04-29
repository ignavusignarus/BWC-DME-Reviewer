// Vitest does not inject a `jest` global, but @testing-library/dom's
// waitFor implementation calls `jest.advanceTimersByTime()` when it detects
// fake timers are active (via setTimeout.clock property).  Alias `jest` → `vi`
// so those internal calls work correctly.
import { vi } from 'vitest';
global.jest = vi;
