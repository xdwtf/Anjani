import asyncio
import os
import re
from io import BytesIO
from urllib.error import HTTPError
from PIL import Image, ImageDraw, ImageFont
from urllib.request import urlopen
import lastfm

ALBUM_COVER_SIZE = (300, 300)


class Fetcher:
    def __init__(self, user: str, period: str, chart_shape: str):
        self.client = lastfm.Client(lastfm_api_key)
        self.user = user
        try:
            self.period = period
            self.chart_shape = chart_shape
        except ValueError as e:
            raise e
        self.albums_number = self._calculate_albums_number()
        self.chart_size = self._calculate_chart_size()

    def _calculate_albums_number(self) -> int:
        return self.chart_shape[0] * self.chart_shape[1]

    def _calculate_chart_size(self) -> tuple[int, int]:
        return (
            ALBUM_COVER_SIZE[0] * self.chart_shape[0],
            ALBUM_COVER_SIZE[1] * self.chart_shape[1],
        )

    async def fetch(self) -> dict:
        user_top_albums = await self.client.user_get_top_albums(
            self.user, self.period, limit=self.albums_number
        )
        return user_top_albums


class Chart:
    font = ImageFont.truetype("/app/anjani/custom_plugins/NotoSansMongolian-Regular.ttf", 15)

    def __init__(self, user_top_albums: dict, chart_size: tuple[int, int]):
        self.size = chart_size
        self.position = (0, 0)
        unfiltered_albums = user_top_albums["topalbums"]["album"]
        self.albums = [self._filter_album_info(album) for album in unfiltered_albums if album["image"][3]["#text"]]

    def _filter_album_info(self, album: dict) -> dict:
        if "image" in album and len(album["image"]) > 3 and album["image"][3]["#text"]:
            return {
                "artist": album["artist"]["name"],
                "album": album["name"],
                "pic": album["image"][3]["#text"],
                "playcount": album["playcount"],
            }
        return {}

    def _get_album_cover(self, album: dict) -> Image:
        try:
            album_cover = Image.open(BytesIO(urlopen(album["pic"]).read()))
        except (ValueError, HTTPError):
            album_cover = Image.new("RGB", ALBUM_COVER_SIZE, "black")
        return album_cover

    def _write_album_info(self, album: dict, album_cover: Image) -> Image:
        text = f"{album['artist']}\n{album['album']}\n{album['playcount']}"
        draw = ImageDraw.Draw(album_cover, "RGBA")
        bbox = draw.textbbox((0, 0), text, font=self.font)
        x, y, width, height = bbox
        text_width = width - x
        text_height = height - y + 10  # Add some extra space for playcount
        x = 0  # Left alignment
        y = ALBUM_COVER_SIZE[1] - text_height  # Bottom alignment
        draw.rectangle((x, y, x + text_width, y + text_height), fill=(0, 0, 0, 128))
        draw.text((x, y), text, (255, 255, 255), self.font)
        return album_cover


    def make_chart(self) -> bytes:
        chart = None
        current_position = self.position  # Store the initial position
        albums_with_images = [album for album in self.albums if self._get_album_cover(album).mode == 'RGB']

        num_albums = len(albums_with_images)
        if num_albums == 0:
            return b''  # Return an empty image if there are no albums with images

        # Calculate the number of columns needed for the available albums
        num_cols = min(num_albums, self.size[0] // ALBUM_COVER_SIZE[0])
        num_rows = -(-num_albums // num_cols)

        # Calculate the actual size needed for the chart based on available albums
        actual_chart_size = (
            num_cols * ALBUM_COVER_SIZE[0],
            num_rows * ALBUM_COVER_SIZE[1]
        )

        # Create a new image with the adjusted size
        chart = Image.new("RGB", actual_chart_size)

        for album in albums_with_images:
            album_cover = self._get_album_cover(album)
            album_cover = self._write_album_info(album, album_cover)
            chart.paste(album_cover, current_position)

            current_position = list(current_position)
            current_position[0] += ALBUM_COVER_SIZE[0]

            if (albums_with_images.index(album) + 1) % num_cols == 0:
                current_position[0] = 0
                current_position[1] += ALBUM_COVER_SIZE[1]

            current_position = tuple(current_position)

        chart_byte_arr = BytesIO()
        chart.save(chart_byte_arr, "PNG")

        # Set the name attribute for in-memory upload
        chart_byte_arr.name = "custom_image.png"

        # Reset the stream position to the beginning
        chart_byte_arr.seek(0)

        return chart_byte_arr


async def create_album_chart(lastfm_api_key, lastfm_user, period, chart_shape):
    client = lastfm.Client(lastfm_api_key)
    try:
        fetcher = Fetcher(lastfm_user, period, chart_shape)
    except ValueError as e:
        return str(e)
    finally:
        pass

    try:
        user_top_albums = await fetcher.fetch()
        chart = Chart(user_top_albums, fetcher.chart_size).make_chart()
        return chart
    finally:
        if client._session:  # Check if the session exists
            await client._session.close()  # Close the client session manually

"""
LASTFM_API_KEY = ""
LASTFM_USER = ""

period = "overall"  # Specify the period (day, week, month, year, overall)
chart_shape = "7x7"  # Specify the chart shape (10x10, 8x10, 20x5)
image_data = await create_album_chart(LASTFM_API_KEY, LASTFM_USER, period, chart_shape)  # Use 'await' as it's an async function
image = Image.open(BytesIO(image_data))
# Save the generated image
image.save("generated_album_chart.jpeg")
image.show()  # Show the generated image
"""
