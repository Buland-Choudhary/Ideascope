/**
 * A minimal, controllable stand-in for the browser's `SpeechSynthesis` API —
 * jsdom doesn't implement it. Install via `installFakeSpeechSynthesis()`
 * (call in `beforeEach`), then inspect `FakeSpeechSynthesis.instance.spoken`
 * and `.cancelCount`.
 */
export class FakeSpeechSynthesis {
  static instance: FakeSpeechSynthesis | null = null;

  spoken: string[] = [];
  cancelCount = 0;

  speak(utterance: { text: string }): void {
    this.spoken.push(utterance.text);
  }

  cancel(): void {
    this.cancelCount += 1;
  }
}

class FakeSpeechSynthesisUtterance {
  text: string;
  constructor(text: string) {
    this.text = text;
  }
}

/** Stubs `window.speechSynthesis`/`SpeechSynthesisUtterance`; returns the instance. */
export function installFakeSpeechSynthesis(
  vi: { stubGlobal: (name: string, value: unknown) => void },
): FakeSpeechSynthesis {
  const instance = new FakeSpeechSynthesis();
  FakeSpeechSynthesis.instance = instance;
  vi.stubGlobal("speechSynthesis", instance);
  vi.stubGlobal("SpeechSynthesisUtterance", FakeSpeechSynthesisUtterance);
  return instance;
}
