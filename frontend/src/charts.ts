import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { COLORS } from "./format";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
);

const sans = '"Inter Variable", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

Chart.defaults.font.family = sans;
Chart.defaults.font.size = 12;
Chart.defaults.color = COLORS.muted;
Chart.defaults.borderColor = COLORS.rule;
Chart.defaults.animation = false;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.plugins.legend.position = "bottom";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 7;
Chart.defaults.plugins.legend.labels.boxHeight = 7;
Chart.defaults.plugins.legend.labels.padding = 18;
Chart.defaults.plugins.tooltip.backgroundColor = "#ffffff";
Chart.defaults.plugins.tooltip.titleColor = COLORS.ink;
Chart.defaults.plugins.tooltip.bodyColor = COLORS.ink;
Chart.defaults.plugins.tooltip.borderColor = COLORS.rule;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.boxPadding = 4;
Chart.defaults.plugins.tooltip.usePointStyle = true;
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 12;
Chart.defaults.plugins.tooltip.titleFont = { family: sans, weight: 600, size: 12 };
Chart.defaults.plugins.tooltip.bodyFont = { family: sans, size: 12 };
