comparison_plot <- function(data, p25, p75, median, ylab, free_y = FALSE) {
  ggplot(data, aes(x = network_size, col = label, fill = label, group = label)) +
    geom_ribbon(
      aes(ymin = {{ p25 }}, ymax = {{ p75 }}),
      col = 'lightgray', alpha = 0.5
    ) +
    geom_point(aes(y = {{ p25 }}), col = 'darkgray', size = 10, shape = '-') +
    geom_point(aes(y = {{ p75 }}), col = 'darkgray', size = 10, shape = '-') +
    geom_line(aes(y = {{ median }})) +
    geom_point(aes(y = {{ median }})) +
    ylab(ylab) +
    xlab('network size') +
    theme_minimal(base_size = 15) +
    facet_grid(
      scales = if (free_y) 'free_y' else 'fixed',
      file_size ~ seeder_ratio,
      labeller = labeller(
        seeder_ratio = as_labeller(function(x) {
          paste0("seeder ratio: ", scales::percent(as.numeric(x)))
        }),
      )
    ) +
    scale_color_discrete(name = '') +
    guides(fill = 'none', alpha = 'none')
}

Y_BPS <- scale_y_continuous(labels = function(x) paste0(scales::label_bytes()(x), '/s'))
Y_TIMESPAN <- scale_y_continuous(labels = scales::label_timespan())
