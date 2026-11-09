/** AG-038: visual E0/E1/E2 and commercial categories must never mix. */
export type ReviewAction = 'confirm' | 'correct' | 'initial_label' | 'no_evaluable'
export type ReviewGrade = 'E0' | 'E1' | 'E2' | 'primera' | 'segunda'

export function possibleActions(currentValue: string | null): ReviewAction[] {
  return currentValue === null
    ? ['initial_label', 'no_evaluable']
    : ['confirm', 'correct', 'no_evaluable']
}

export function gradeOptions(currentValue: string | null): ReviewGrade[] {
  return currentValue === 'primera' || currentValue === 'segunda'
    ? ['primera', 'segunda']
    : ['E0', 'E1', 'E2']
}

export function canSubmitDecision(action: ReviewAction, previous: string | null, newValue: string): boolean {
  if (action === 'no_evaluable') return true
  if (action === 'initial_label') return previous === null && ['E0', 'E1', 'E2'].includes(newValue)
  if (action === 'confirm') return previous !== null && previous === newValue
  if (action === 'correct') return previous !== null && previous !== newValue
    && gradeOptions(previous).includes(newValue as ReviewGrade)
  return false
}
