export interface TermItem {
  source: string;
  suggested: string;
  translation: string;
  preserve: boolean;
  count: number;
  category: string;
  context: string;
}

export interface TranslationFailure {
  index: number;
  message: string;
}

export type TranslationEvent =
  | { type: "start"; total: number }
  | { type: "block_start"; index: number; total: number }
  | { type: "delta"; index: number; text: string }
  | { type: "block_reset"; index: number; message: string }
  | { type: "block"; index: number; total: number; translation: string }
  | { type: "block_error"; index: number; total: number; message: string }
  | { type: "complete"; translation: string; errors: TranslationFailure[] }
  | { type: "fatal_error"; message: string };
