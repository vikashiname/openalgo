export const formatPrice = (value: number | null | undefined): string => {
  if (value == null) return '-';
  return value.toFixed(2);
};

export const formatIst = (value: number | null | undefined): string => {
  if (value == null) return '-';
  return value.toFixed(2);
};

export const formatPnl = (value: number | null | undefined): string => {
  if (value == null) return '-';
  const formatted = value.toFixed(2);
  return value >= 0 ? `+${formatted}` : formatted;
};
