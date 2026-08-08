export function isPresent(value: string): boolean {
  return value.trim().length > 0
}

export function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}
