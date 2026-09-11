type PaginationProps = {
  disabled: boolean;
  page: number;
  totalCount: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
};

export function Pagination({ disabled, page, totalCount, totalPages, onPrevious, onNext }: PaginationProps) {
  return (
    <nav aria-label="Pagination" className="pagination">
      <button className="button button--secondary" disabled={disabled || page <= 1} type="button" onClick={onPrevious}>
        Previous
      </button>
      <span className="pagination__info">Page {page} of {totalPages} · {totalCount} items</span>
      <button className="button button--secondary" disabled={disabled || page >= totalPages} type="button" onClick={onNext}>
        Next
      </button>
    </nav>
  );
}
