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

const serif = 'Georgia, "Times New Roman", Times, serif';

Chart.defaults.font.family = serif;
Chart.defaults.font.size = 12;
Chart.defaults.color = COLORS.muted;
Chart.defaults.borderColor = COLORS.rule;
Chart.defaults.animation = false;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.plugins.legend.position = "bottom";
Chart.defaults.plugins.legend.labels.boxWidth = 14;
Chart.defaults.plugins.legend.labels.boxHeight = 8;
Chart.defaults.plugins.tooltip.backgroundColor = "#fffdf8";
Chart.defaults.plugins.tooltip.titleColor = COLORS.ink;
Chart.defaults.plugins.tooltip.bodyColor = COLORS.ink;
Chart.defaults.plugins.tooltip.borderColor = COLORS.sand;
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.titleFont = { family: serif, weight: "bold", size: 13 };
Chart.defaults.plugins.tooltip.bodyFont = { family: serif, size: 12 };
