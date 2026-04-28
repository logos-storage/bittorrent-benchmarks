is_completed <- function(completion) abs(1.0 - completion) < 1e-7

#' Extracts repetition id and seed set id from the dataset name,
#' which should be in the format `dataset-<seed_set>-<repetition>`.
#'
#' @param download_metric
#' @param meta
#'
#' @returns
#' @export
extract_repetitions <- function(download_metric) {
  download_metric |>
    mutate(
      temp = str_remove(dataset_name, '^dataset-'),
      seed_set = as.numeric(str_extract(temp, '^\\d+')),
      run = as.numeric(str_extract(temp, '\\d+$'))
    ) |>
    rename(piece = value) |>
    select(-temp, -name)
}

#' Computes the progress, in percentage, of the download. The underlying
#' assumption is that downloads are logged as discrete chunks of the same size,
#' and that the `value` column contains something that identifies this chunk.
#'
#' This makes it compatible with BitTorrent, which logs piece ids, whereas with
#' other systems we can simply use a byte count, provided the logger is smart
#' enough to log at equally-sized, discrete intervals.
#'
compute_progress <- function(download_metric, meta, count_distinct) {
  download_metric |>
    group_by(node, seed_set, run) |>
    arrange(timestamp) |>
    mutate(
      piece_count = if (count_distinct) seq_along(timestamp) else piece
    ) |>
    ungroup() |>
    mutate(completed = (as.integer64(piece_count) * meta$download_metric_unit_bytes) / meta$file_size)
}

process_incomplete_downloads <- function(download_metric, discard_incomplete) {
  incomplete_downloads <- download_metric |>
    group_by(node, seed_set, run) |>
    summarise(completed = max(completed)) |>
    filter(!is_completed(completed))

  if(nrow(incomplete_downloads) > 0) {
    (if (!discard_incomplete) stop else warning)(
      'Experiment contained incomplete downloads.')
  }

  download_metric |> anti_join(
    incomplete_downloads, by = c('node', 'seed_set', 'run'))
}

process_incomplete_repetitions <- function(download_metric, repetitions, allow_missing) {
  mismatching_repetitions <- download_metric |>
    select(seed_set, node, run) |>
    distinct() |>
    group_by(seed_set, node) |>
    count() |>
    filter(n != repetitions)

  if(nrow(mismatching_repetitions) > 0) {
    (if (!allow_missing) stop else warning)(
      'Experiment data did not have all repetitions.')
  }

  download_metric
}

compute_download_times <- function(meta, request_event, download_metric, group_id) {
  n_leechers <- meta$nodes$network_size - meta$seeders

  download_start <- request_event |>
    select(-request_id) |>
    filter(name == 'leech', type == 'EventBoundary.start') |>
    mutate(
      # We didn't log those on the runner side so I have to reconstruct them.
      run = rep(rep(
        1:meta$repetitions - 1,
        each = n_leechers), times = meta$seeder_sets),
      seed_set = rep(
        1:meta$seeder_sets - 1,
        each = n_leechers * meta$repetitions),
      destination = gsub('"', '', destination) # sometimes we get double-quoted strings in logs
    ) |>
    transmute(node = destination, run, seed_set, seed_request_time = timestamp)

  download_times <- download_metric |>
    left_join(download_start, by = c('node', 'run', 'seed_set')) |>
    mutate(
      elapsed_download_time = as.numeric(timestamp - seed_request_time)
    ) |>
    group_by(node, run, seed_set) |>
    mutate(
      # The time elapsed between the instant we start the download and the time
      # we see the first log entry is approximated as "time to first byte".
      # In reality, this factors lookup time, swarm bootstrap time, and
      # part of the download itself.
      first_byte_t = min(timestamp),
      first_byte = as.numeric(first_byte_t - seed_request_time),
      # "Transfer" time is the total download time minus the lookup time. Again,
      # this is approximated, and likely reflects a shorter download time than
      # the real download time.
      transfer = as.numeric(max(timestamp) - first_byte_t)
    ) |>
    ungroup()

  if (nrow(download_times |>
           filter(elapsed_download_time < 0 | first_byte < 0 | transfer < 0)) > 0) {
    stop('Calculation for download times contains negative numbers')
  }

  download_times
}


download_times <- function(experiment, piece_count_distinct, discard_incomplete = TRUE, allow_missing = TRUE) {
  meta <- experiment$meta
  downloads <- experiment$download_metric |>
    extract_repetitions() |>
    compute_progress(meta, count_distinct = piece_count_distinct)

  downloads <- process_incomplete_downloads(
    downloads,
    discard_incomplete
  ) |>
    process_incomplete_repetitions(meta$repetitions, allow_missing)

  download_times <- compute_download_times(
    meta,
    experiment$request_event,
    downloads,
    group_id
  )

  if (!check_seeder_count(download_times, meta$seeders)) {
    warning(glue::glue('Undefined download times do not match seeder count'))
    return(NULL)
  }

  download_times
}


completion_time_stats <- function(download_times, meta) {
  filtered <- download_times |>
    filter(!is.na(elapsed_download_time),
           is_completed(completed))

  n_experiments <- meta$repetitions * meta$seeder_sets
  n_leechers <- meta$nodes$network_size - meta$seeders
  n_points <- n_experiments * n_leechers

  tibble(
    n = nrow(filtered),
    expected_n = n_points,
    missing = expected_n - n,
    completion = distributional_stats(filtered$elapsed_download_time),
    first_byte = distributional_stats(filtered$first_byte),
    transfer = distributional_stats(filtered$transfer)
  ) |>
    unnest(
      cols = c(completion, first_byte, transfer),
      names_sep = '_'
    )
}

distributional_stats <- function(x) {
  n <- length(x)
  tibble(
    min = min(x),
    p05 = quantile(x, p = 0.05),
    p10 = quantile(x, p = 0.10),
    p20 = quantile(x, p = 0.20),
    p25 = quantile(x, p = 0.25),
    median = median(x),
    p75 = quantile(x, p = 0.75),
    p80 = quantile(x, p = 0.80),
    p90 = quantile(x, p = 0.90),
    p95 = quantile(x, p = 0.95),
    max = max(x),
    iqr = p75 - p25,
    # This gives us roughly a 95% ci for comparing medians.
    ci = (1.58 * iqr) / sqrt(n),
    w_top = median + ci,
    w_bottom = median - ci
  )

}

check_seeder_count <- function(download_times, seeders) {
  mismatching_seeders <- download_times |>
    filter(is.na(seed_request_time)) |>
    select(node, seed_set, run) |>
    distinct() |>
    group_by(seed_set, run) |>
    count() |>
    filter(n != seeders)

  nrow(mismatching_seeders) == 0
}

download_stats <- function(download_times) {
  download_times |>
    filter(!is.na(elapsed_download_time)) |>
    group_by(piece_count, completed) |>
    summarise(
      mean = mean(elapsed_download_time),
      median = median(elapsed_download_time),
      max = max(elapsed_download_time),
      min = min(elapsed_download_time),
      p90 = quantile(elapsed_download_time, p = 0.95),
      p10 = quantile(elapsed_download_time, p = 0.05),
      .groups = 'drop'
    )
}

compute_compact_summary <- function(download_ecdf) {
  lapply(c(0.05, 0.5, 0.95), function(p)
    download_ecdf |>
      filter(completed >= p) |>
      slice_min(completed)
  ) |>
    bind_rows() |>
    select(completed, network_size, file_size, seeders, leechers, median) |>
    pivot_wider(id_cols = c('file_size', 'network_size', 'seeders', 'leechers'),
                names_from = completed, values_from = median)
}

compute_speedups <- function(benchmarks, baseline, compare) {
  baseline_data <- benchmarks |>
    filter(label == baseline) |>
    select(
      experiment_type, label, network_size, seeders, leechers, file_size, completion_median
    ) |>
    rename(baseline_median = completion_median)


  lapply(compare, function(compare_label) {
    benchmarks |>
      filter(label == compare_label) |>
      inner_join(
        baseline_data,
        by = c('network_size', 'seeders', 'leechers', 'file_size')
      ) |>
      mutate(
        relative_median = completion_median / baseline_median
      ) |>
      mutate(label = label.x) |>
      select(-baseline_median, -label.y, -label.x)
  }) |>
    bind_rows()
}
