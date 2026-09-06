export class TargetOperationGuard {
  private readonly activeTargetIds = new Set<number>();

  begin(targetId: number) {
    if (this.activeTargetIds.has(targetId)) return false;
    this.activeTargetIds.add(targetId);
    return true;
  }

  finish(targetId: number) {
    this.activeTargetIds.delete(targetId);
  }
}
