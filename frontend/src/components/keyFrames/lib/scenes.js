export function sceneFor(intervals, timestamp) {
  if (!Array.isArray(intervals) || !intervals.length) {
    return null;
  }

  let index = intervals.findIndex(
    (interval) => timestamp >= interval[0] && timestamp < interval[1],
  );

  if (index === -1) {
    index = intervals.length - 1;
  }

  return {
    number: index + 1,
    start: intervals[index][0],
    end: intervals[index][1],
  };
}