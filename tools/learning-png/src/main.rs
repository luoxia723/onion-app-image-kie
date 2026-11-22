// SPDX-License-Identifier: AGPL-3.0-only
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, Write};
use zenquant::{OutputFormat, QuantizeConfig};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let [input, width, height, colors, format] = args.as_slice() else {
        return Err("expected input.rgb width height colors min|joint".into());
    };
    let width: usize = width.to_string_lossy().parse()?;
    let height: usize = height.to_string_lossy().parse()?;
    let pixels = width
        .checked_mul(height)
        .filter(|size| (1..=40_000_000).contains(size))
        .ok_or("invalid image size")?;
    let colors: u32 = colors.to_string_lossy().parse()?;
    if !(2..=256).contains(&colors) || fs::metadata(input)?.len() != (pixels * 3) as u64 {
        return Err("invalid color budget or RGB length".into());
    }
    let format = match format.to_str() {
        Some("min") => OutputFormat::PngMinSize,
        Some("joint") => OutputFormat::PngJoint,
        _ => return Err("expected min or joint optimization".into()),
    };
    let input = fs::read(input)?;
    let pixels: Vec<_> = input
        .chunks_exact(3)
        .map(|pixel| rgb::RGB::new(pixel[0], pixel[1], pixel[2]))
        .collect();
    let palette = zenquant::quantize(
        &pixels,
        width,
        height,
        &QuantizeConfig::new(format).with_max_colors(colors),
    )?;

    // Output is a little-endian palette length, RGB palette and one index per pixel.
    let mut output = io::BufWriter::new(io::stdout().lock());
    output.write_all(&(palette.palette().len() as u16).to_le_bytes())?;
    for color in palette.palette() {
        output.write_all(color)?;
    }
    output.write_all(palette.indices())?;
    output.flush()?;
    Ok(())
}
